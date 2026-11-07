# Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE.
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

import requests

DEFAULT_TIMEOUT = 60
MODEL_CACHE_TTL_SECONDS = 600


def _iso_now():
    return datetime.now(timezone.utc).isoformat()


class OpenRouterClient:
    def __init__(self, api_key: Optional[str] = None, site_url: Optional[str] = None):
        self.api_key = (api_key or os.getenv("OPENROUTER_API_KEY", "")).strip()
        self.site_url = (site_url or os.getenv("SITE_URL", "http://localhost:5000")).strip()
        self.base_url = "https://openrouter.ai/api/v1"
        self._model_cache: Optional[Dict[str, Any]] = None
        self._model_cache_time: float = 0

    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": self.site_url,
            "X-Title": "Lesmarl AI",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def get_public_models(self) -> Dict[str, Any]:
        now = time.time()
        if self._model_cache and (now - self._model_cache_time) < MODEL_CACHE_TTL_SECONDS:
            return self._model_cache

        payload = {"models": [], "default": "", "cached_at": _iso_now()}
        try:
            response = requests.get(f"{self.base_url}/models", timeout=10)
            response.raise_for_status()
            data = response.json()
            items = data.get("data", []) if isinstance(data, dict) else []
            filtered = []
            for item in items:
                if not isinstance(item, dict):
                    continue
                price = item.get("pricing") or {}
                if not isinstance(price, dict):
                    continue
                try:
                    prompt = float(price.get("prompt", 0) or 0)
                    completion = float(price.get("completion", 0) or 0)
                except (TypeError, ValueError):
                    continue
                if prompt > 0 or completion > 0:
                    continue
                model_id = item.get("id")
                name = item.get("name") or model_id or "Unnamed model"
                context = int(item.get("context_length") or 0)
                description = item.get("description") or "OpenRouter free model"
                filtered.append({
                    "id": model_id,
                    "name": name,
                    "context_length": context,
                    "description": description[:140],
                })
            filtered = sorted(filtered, key=lambda item: (item.get("context_length") or 0, item.get("id") or ""), reverse=True)
            default_id = os.getenv("DEFAULT_MODEL", "").strip()
            if not default_id and filtered:
                default_id = filtered[0].get("id", "")
            payload["models"] = filtered
            payload["default"] = default_id
            self._model_cache = payload
            self._model_cache_time = now
        except requests.RequestException:
            if self._model_cache:
                return self._model_cache
            payload["models"] = []
            payload["default"] = os.getenv("DEFAULT_MODEL", "").strip()
        self._model_cache = payload
        self._model_cache_time = now
        return payload

    def enhance_prompt(self, prompt: str, model: Optional[str] = None) -> str:
        if not self.api_key:
            raise RuntimeError("OpenRouter API is not configured.")
        selected_model = model or os.getenv("DEFAULT_MODEL", "").strip()
        if not selected_model:
            raise RuntimeError("No default model is configured.")
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json={
                "model": selected_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Rewrite the user's prompt to make it clearer, more specific, and well-structured. Preserve the user's intent and facts. Return only the revised prompt; do not answer it.",
                    },
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.3,
                "max_tokens": 700,
                "stream": False,
            },
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        choices = payload.get("choices", [])
        if not choices:
            raise ValueError("The model returned no enhanced prompt.")
        content = choices[0].get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("The model returned no enhanced prompt.")
        return content.strip()

    def stream_chat(self, messages: List[Dict[str, str]], model: Optional[str] = None, temperature: float = 0.7, max_tokens: int = 4096, fallback_models: Optional[List[str]] = None):
        if not self.api_key:
            raise RuntimeError("OpenRouter API key is not configured.")

        selected_model = model or os.getenv("DEFAULT_MODEL", "").strip() or "openai/gpt-4o-mini:free"
        candidates: List[str] = []
        seen = set()
        if selected_model:
            candidates.append(selected_model)
        for fallback in fallback_models or []:
            if fallback and fallback not in seen and fallback != selected_model:
                candidates.append(fallback)
                seen.add(fallback)

        if not candidates:
            candidates = ["openai/gpt-4o-mini:free"]

        fallback_used = False
        last_error = None
        for index, candidate in enumerate(candidates):
            payload = {
                "model": candidate,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            received_content = False
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions",
                    headers=self._headers({"Accept": "text/event-stream"}),
                    json=payload,
                    timeout=60,
                    stream=True,
                )
                if response.status_code in (404, 429, 500, 502, 503, 504):
                    last_error = response.text
                    if index < len(candidates) - 1:
                        fallback_used = True
                        continue
                    raise requests.HTTPError(f"OpenRouter error {response.status_code}")
                response.raise_for_status()
                response.encoding = "utf-8"
                start = time.time()
                first_token_ms = None
                truncated = False
                saw_done_marker = False
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            saw_done_marker = True
                            break
                        try:
                            chunk = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk.get("choices", [])
                        if not choices:
                            continue
                        if choices[0].get("finish_reason") == "length":
                            truncated = True
                        delta = choices[0].get("delta", {})
                        token = delta.get("content") or ""
                        if token:
                            received_content = True
                            if first_token_ms is None:
                                first_token_ms = int((time.time() - start) * 1000)
                            yield {"event": "token", "text": token}
                if not saw_done_marker:
                    raise RuntimeError("The model response was incomplete because the stream ended early. Please retry.")
                if not received_content:
                    if index < len(candidates) - 1:
                        fallback_used = True
                        continue
                    raise RuntimeError("OpenRouter returned no content for this request. Try again or switch models.")
                usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                yield {"event": "done", "usage": usage, "model": candidate, "truncated": truncated, "ms_first_token": first_token_ms or 0, "ms_total": int((time.time() - start) * 1000)}
                return
            except requests.RequestException as exc:
                if received_content:
                    raise RuntimeError("The model connection ended before the answer was complete. Please retry.") from exc
                last_error = str(exc)
                if index < len(candidates) - 1:
                    fallback_used = True
                    continue
                raise
        if last_error is not None:
            raise RuntimeError(last_error)
        raise RuntimeError("No OpenRouter model available.")
