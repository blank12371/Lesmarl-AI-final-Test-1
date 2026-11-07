# Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE.
import json
import sqlite3
from pathlib import Path

import requests

from app import create_app
from openrouter_client import OpenRouterClient


def _make_client(monkeypatch, api_key="test-key", database_path=None):
    monkeypatch.setenv("OPENROUTER_API_KEY", api_key)
    monkeypatch.setenv("DEFAULT_MODEL", "meta-llama/llama-3.1-8b-instruct:free")
    monkeypatch.setenv("FALLBACK_MODELS", "google/gemma-3-4b-it:free,mistralai/mistral-7b-instruct:free")
    if database_path is not None:
        monkeypatch.setenv("DATABASE_PATH", str(database_path))
    return create_app()


def _register_user(client, name="Test User", password="correct-horse-battery"):
    csrf_token = client.get("/api/auth/me").get_json()["csrf_token"]
    response = client.post(
        "/api/auth/register",
        json={"name": name, "password": password},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201
    return response.get_json()


def _mock_free_model_catalog(monkeypatch, model_ids=None):
    model_ids = model_ids or ["meta-llama/llama-3.1-8b-instruct:free"]
    model_data = {
        "models": [{"id": model_id, "name": model_id} for model_id in model_ids],
        "default": model_ids[0] if model_ids else "",
    }
    monkeypatch.setattr(OpenRouterClient, "get_public_models", lambda self: model_data)


def test_valid_chat_request_streams_events(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    _mock_free_model_catalog(monkeypatch)
    captured = {}

    def fake_stream_chat(self, messages, model=None, temperature=0.7, max_tokens=512, fallback_models=None):
        captured["fallback_models"] = fallback_models
        yield {"event": "meta", "model": model or "meta-llama/llama-3.1-8b-instruct:free", "fallback_used": False}
        yield {"event": "token", "text": "Hello"}
        yield {"event": "done", "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}, "model": model or "meta-llama/llama-3.1-8b-instruct:free", "ms_first_token": 10, "ms_total": 20}

    monkeypatch.setattr(OpenRouterClient, "stream_chat", fake_stream_chat)

    client = app.test_client()
    _register_user(client)
    response = client.post(
        "/api/chat",
        json={
            "model": "meta-llama/llama-3.1-8b-instruct:free",
            "messages": [{"role": "user", "content": "hello"}],
            "temperature": 0.7,
            "max_tokens": 128,
        },
    )

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert "event: meta" in body
    assert "event: token" in body
    assert "event: done" in body
    assert captured["fallback_models"] == []


def test_chat_api_reports_incomplete_upstream_response(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    _mock_free_model_catalog(monkeypatch)

    class PartialResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter(['data: {"choices":[{"delta":{"content":"The answer ends"}}]}'])

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: PartialResponse())
    client = app.test_client()
    _register_user(client)
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Explain fully."}]})
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "event: token" in body
    assert "event: error" in body
    assert "incomplete" in body.lower()
    assert "event: done" not in body


def test_invalid_payloads_and_missing_key(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    client = app.test_client()
    _register_user(client)

    bad_json = client.post("/api/chat", data="not-json", content_type="text/plain")
    assert bad_json.status_code == 415

    too_many = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}] * 61})
    assert too_many.status_code == 400

    oversize = client.post("/api/chat", json={"messages": [{"role": "user", "content": "x" * 20001}]})
    assert oversize.status_code == 413

    wrong_role = client.post("/api/chat", json={"messages": [{"role": "bot", "content": "hi"}]})
    assert wrong_role.status_code == 400

    out_of_range_temp = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}], "temperature": 3})
    assert out_of_range_temp.status_code == 400

    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "missing-key-users.sqlite3"))
    app2 = create_app()
    client2 = app2.test_client()
    _register_user(client2)
    no_key = client2.post("/api/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert no_key.status_code == 503

    health = app2.test_client().get("/health")
    assert health.status_code == 200
    payload = health.get_json()
    assert payload["api_key_configured"] is False


def test_models_are_filtered_and_cached(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")

    class FakeResponse:
        def __init__(self, payload):
            self._payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self._payload

    def fake_get(url, timeout=10):
        return FakeResponse({
            "data": [
                {"id": "paid/model", "name": "Paid", "context_length": 32_000, "pricing": {"prompt": 0.02, "completion": 0.04}},
                {"id": "unknown-price/model", "name": "Unknown Price", "context_length": 48_000, "pricing": {"prompt": -1, "completion": -1}, "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}},
                {"id": "free/model", "name": "Free", "context_length": 64_000, "pricing": {"prompt": 0, "completion": 0}, "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]}},
                {"id": "other-free", "name": "Other Free", "context_length": 128_000, "pricing": {"prompt": 0, "completion": 0}, "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]}},
                {"id": "free-audio", "name": "Audio Generator", "context_length": 16_000, "pricing": {"prompt": 0, "completion": 0}, "architecture": {"input_modalities": ["text"], "output_modalities": ["text", "audio"]}},
            ]
        })

    monkeypatch.setattr("requests.get", fake_get)
    response = app.test_client().get("/api/models")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["default"] == "other-free"
    assert all(model["id"] != "paid/model" for model in payload["models"])
    assert all(model["id"] != "unknown-price/model" for model in payload["models"])
    assert all(model["id"] != "free-audio" for model in payload["models"])
    assert any(item["id"] == "other-free" for item in payload["models"])
    model_ids = {item["id"] for item in payload["models"]}
    assert "google/gemini-pro-1.5" not in model_ids
    assert "meta-llama/llama-3.1-70b-instruct:free" not in model_ids
    assert "deepseek/deepseek-chat" not in model_ids


def test_chat_rejects_model_outside_free_catalog(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    _mock_free_model_catalog(monkeypatch)
    monkeypatch.setattr(OpenRouterClient, "stream_chat", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Paid model must not be called.")))
    client = app.test_client()
    _register_user(client)

    response = client.post("/api/chat", json={
        "model": "deepseek/deepseek-chat",
        "messages": [{"role": "user", "content": "Do not send this to a paid model."}],
    })

    assert response.status_code == 400
    assert "free" in response.get_json()["error"]["message"].lower()


def test_enhance_rejects_model_outside_free_catalog(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    _mock_free_model_catalog(monkeypatch)
    monkeypatch.setattr(OpenRouterClient, "enhance_prompt", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Paid model must not be called.")))
    client = app.test_client()
    _register_user(client)
    csrf_token = client.get("/api/auth/me").get_json()["csrf_token"]

    response = client.post("/api/enhance", json={
        "prompt": "Improve this prompt.",
        "model": "deepseek/deepseek-chat",
    }, headers={"X-CSRF-Token": csrf_token})

    assert response.status_code == 400
    assert "free" in response.get_json()["error"]["message"].lower()


def test_chat_requests_allow_longer_responses(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    _mock_free_model_catalog(monkeypatch)
    captured = {}

    def fake_stream_chat(self, messages, model=None, temperature=0.7, max_tokens=512, fallback_models=None):
        captured["max_tokens"] = max_tokens
        yield {"event": "token", "text": "Longer answer"}
        yield {"event": "done", "model": model, "usage": {}, "ms_first_token": 1, "ms_total": 2}

    monkeypatch.setattr(OpenRouterClient, "stream_chat", fake_stream_chat)
    client = app.test_client()
    _register_user(client)
    response = client.post("/api/chat", json={"messages": [{"role": "user", "content": "Explain this in detail."}]})

    assert response.status_code == 200
    response.get_data(as_text=True)
    assert captured["max_tokens"] >= 2048


def test_empty_stream_is_reported_rather_than_silently_returning(monkeypatch):
    calls = []

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter([
                'data: {"choices":[{"delta":{"role":"assistant"}}]}',
                'data: [DONE]',
            ])

    def fake_post(url, headers=None, json=None, timeout=None, stream=True):
        calls.append(json["model"])
        return FakeResponse()

    monkeypatch.setattr("requests.post", fake_post)
    client = OpenRouterClient(api_key="test-key", site_url="http://localhost")

    try:
        list(client.stream_chat([
            {"role": "user", "content": "hi"}
        ], model="meta-llama/llama-3.1-8b-instruct:free", fallback_models=[]))
        assert False, "Expected a RuntimeError when the model stream produces no content."
    except RuntimeError as exc:
        assert "no content" in str(exc).lower()


def test_retries_on_400_and_then_falls_back(monkeypatch):
    calls = []

    class FakeResponse:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"status {self.status_code}")

        def iter_lines(self, decode_unicode=True):
            return iter([
                'data: {"choices":[{"delta":{"content":"Fallback reply"}}]}',
                'data: [DONE]',
            ])

    def fake_post(url, headers=None, json=None, timeout=None, stream=True):
        calls.append(json["model"])
        if len(calls) == 1:
            return FakeResponse(400, "input too long")
        return FakeResponse(200, "ok")

    monkeypatch.setattr("requests.post", fake_post)
    client = OpenRouterClient(api_key="test-key", site_url="http://localhost")
    stream = list(client.stream_chat([
        {"role": "user", "content": "long file prompt"}
    ], model="bad/model", fallback_models=["good/model"]))
    assert calls == ["bad/model", "good/model"]
    assert any(item.get("event") == "done" for item in stream)


def test_failover_logic(monkeypatch, tmp_path):
    _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")

    calls = []

    class FakeResponse:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text

        def raise_for_status(self):
            if self.status_code >= 400:
                raise requests.HTTPError(f"status {self.status_code}")

        def iter_lines(self, decode_unicode=True):
            if self.status_code == 200:
                return iter([
                    'data: {"choices":[{"delta":{"content":"Hello"}}]}',
                    'data: [DONE]'
                ])
            return iter([])

    def fake_post(url, headers=None, json=None, timeout=None, stream=True):
        calls.append(json["model"])
        if len(calls) == 1:
            return FakeResponse(429, "rate limit")
        return FakeResponse(200, "ok")

    monkeypatch.setattr("requests.post", fake_post)
    client = OpenRouterClient(api_key="test-key", site_url="http://localhost")
    stream = list(client.stream_chat([
        {"role": "user", "content": "hi"}
    ], model="meta-llama/llama-3.1-8b-instruct:free", fallback_models=["google/gemma-3-4b-it:free"]))
    assert calls == ["meta-llama/llama-3.1-8b-instruct:free", "google/gemma-3-4b-it:free"]
    assert any(item.get("event") == "done" for item in stream)


def test_streaming_decodes_utf8_unicode(monkeypatch):
    expected_text = 'Café — “smart”'

    class FakeResponse:
        status_code = 200
        encoding = "ISO-8859-1"

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            event = json.dumps(
                {"choices": [{"delta": {"content": expected_text}}]},
                ensure_ascii=False,
            ).encode("utf-8")
            return iter([
                "data: " + event.decode(self.encoding),
                "data: [DONE]",
            ])

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
    client = OpenRouterClient(api_key="test-key", site_url="http://localhost")
    events = list(client.stream_chat([{"role": "user", "content": "say hello"}], model="test/model"))
    token = next(event["text"] for event in events if event.get("event") == "token")
    assert token == expected_text


def test_stream_reports_provider_output_limit(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter([
                'data: {"choices":[{"delta":{"content":"Partial answer"},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
                'data: [DONE]',
            ])

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
    client = OpenRouterClient(api_key="test-key", site_url="http://localhost")
    events = list(client.stream_chat([{"role": "user", "content": "Explain fully."}], model="test/model"))

    done = next(event for event in events if event.get("event") == "done")
    assert done["truncated"] is True


def test_stream_does_not_mark_early_disconnect_as_complete(monkeypatch):
    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def iter_lines(self, decode_unicode=True):
            return iter([
                'data: {"choices":[{"delta":{"content":"The answer ends"}}]}',
            ])

    monkeypatch.setattr("requests.post", lambda *args, **kwargs: FakeResponse())
    client = OpenRouterClient(api_key="test-key", site_url="http://localhost")

    try:
        list(client.stream_chat([{"role": "user", "content": "Explain fully."}], model="test/model"))
        assert False, "Expected the incomplete upstream stream to raise an error."
    except RuntimeError as exc:
        assert "incomplete" in str(exc).lower()


def test_security_headers_are_present(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    response = app.test_client().get("/")
    headers = response.headers
    assert "Content-Security-Policy" in headers
    assert "X-Content-Type-Options" in headers
    assert "Referrer-Policy" in headers


def test_account_registration_login_and_logout(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    client = app.test_client()
    registration = _register_user(client)
    assert registration["user"]["name"] == "Test User"

    with sqlite3.connect(tmp_path / "users.sqlite3") as connection:
        stored_hash = connection.execute("SELECT password_hash FROM users").fetchone()[0]
    assert stored_hash != "correct-horse-battery"

    csrf_token = client.get("/api/auth/me").get_json()["csrf_token"]
    invalid_login = client.post(
        "/api/auth/login",
        json={"name": "Test User", "password": "wrong-password"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert invalid_login.status_code == 401

    client.post("/api/auth/logout", headers={"X-CSRF-Token": csrf_token})
    signed_out_chat = client.post("/api/chat", json={"messages": [{"role": "user", "content": "hello"}]})
    assert signed_out_chat.status_code == 401

    fresh_client = app.test_client()
    csrf_token = fresh_client.get("/api/auth/me").get_json()["csrf_token"]
    login = fresh_client.post(
        "/api/auth/login",
        json={"name": "Test User", "password": "correct-horse-battery"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert login.status_code == 200
    assert login.get_json()["user"]["name"] == "Test User"


def test_enhance_requires_auth_and_returns_rewritten_prompt(monkeypatch, tmp_path):
    app = _make_client(monkeypatch, database_path=tmp_path / "users.sqlite3")
    client = app.test_client()
    unauthorized = client.post("/api/enhance", json={"prompt": "help me write"})
    assert unauthorized.status_code == 401

    _register_user(client)
    _mock_free_model_catalog(monkeypatch)
    monkeypatch.setattr(OpenRouterClient, "enhance_prompt", lambda self, prompt, model=None: "Write a clear, concise project brief.")
    csrf_token = client.get("/api/auth/me").get_json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf_token}
    response = client.post("/api/enhance", json={"prompt": "help me write"}, headers=headers)
    assert response.status_code == 200
    assert response.get_json() == {"prompt": "Write a clear, concise project brief."}

    invalid = client.post("/api/enhance", json={"prompt": " "}, headers=headers)
    assert invalid.status_code == 400
