# Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE.
import json
import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, session, stream_with_context
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import requests

from config import AppConfig
from openrouter_client import OpenRouterClient


APP_VERSION = "0.1.0"
ALLOWED_ROLES = {"system", "user", "assistant"}
MAX_MESSAGE_COUNT = 60
MAX_MESSAGE_CHARS = 20_000
MAX_BODY_BYTES = 200 * 1024
MAX_COMPLETION_TOKENS = 4096
PASSWORD_ITERATIONS = 310_000


def json_error(code, message, extra=None):
    payload = {"error": {"code": str(code), "message": message}}
    if extra:
        payload["error"].update(extra)
    return jsonify(payload), code


def create_app():
    config = AppConfig()
    openrouter_client = OpenRouterClient(api_key=config.api_key, site_url=config.site_url)
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.secret_key = os.getenv("SESSION_SECRET") or secrets.token_hex(32)
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES
    app.config["VERSION"] = APP_VERSION
    app.config["DEFAULT_MODEL"] = config.default_model
    app.config["FALLBACK_MODELS"] = config.fallback_models
    app.config["OPENROUTER_API_KEY"] = config.api_key
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["SESSION_COOKIE_SECURE"] = config.site_url.startswith("https://")
    database_path = Path(os.getenv("DATABASE_PATH", str(Path(__file__).resolve().with_name("lesmarl.sqlite3"))))
    if str(database_path) != ":memory:":
        database_path.parent.mkdir(parents=True, exist_ok=True)

    def connect_database():
        connection = sqlite3.connect(str(database_path), timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def database_connection():
        connection = connect_database()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    with database_connection() as connection:
        connection.execute(
            "CREATE TABLE IF NOT EXISTS users ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "name TEXT NOT NULL COLLATE NOCASE UNIQUE, "
            "salt TEXT NOT NULL, password_hash TEXT NOT NULL, "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )

    def csrf_token():
        token = session.get("csrf_token")
        if not token:
            token = secrets.token_urlsafe(32)
            session["csrf_token"] = token
        return token

    def csrf_is_valid():
        expected = session.get("csrf_token", "")
        provided = request.headers.get("X-CSRF-Token", "")
        return bool(expected and provided and hmac.compare_digest(expected, provided))

    def user_response(user):
        return {"id": user["id"], "name": user["name"]}

    limiter = Limiter(key_func=get_remote_address, default_limits=[config.rate_limit], storage_uri="memory://")
    limiter.init_app(app)

    @app.after_request
    def add_security_headers(response):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
            "base-uri 'none'; form-action 'self'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "microphone=(self)"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        return response

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/about")
    def about():
        return render_template("about.html")

    @app.route("/privacy")
    def privacy():
        return render_template("privacy.html")

    @app.route("/license")
    def license_page():
        license_text = Path(__file__).resolve().with_name("LICENSE").read_text(encoding="utf-8")
        return render_template("license.html", license_text=license_text)

    @app.route("/robots.txt")
    def robots():
        return Response("User-agent: *\nAllow: /\n", mimetype="text/plain")

    @app.route("/humans.txt")
    def humans():
        return Response("Lesmarl AI\nMade by Mashrur Ahmed Arib\n", mimetype="text/plain")

    @app.route("/.well-known/security.txt")
    def security_txt():
        return Response("Contact: mailto:hello@example.com\nPreferred-Languages: en\nCanonical: https://example.com\nPolicy: https://example.com/privacy\n", mimetype="text/plain")

    @app.route("/api/models")
    @limiter.limit("30/minute")
    def api_models():
        current_config = AppConfig()
        response = openrouter_client.get_public_models()
        models = response.get("models", [])
        available_ids = {item.get("id") for item in models if isinstance(item, dict)}
        default_value = current_config.default_model
        if default_value not in available_ids:
            default_value = response.get("default")
        if default_value not in available_ids:
            default_value = models[0]["id"] if models else ""
        response["default"] = default_value
        return jsonify(response)

    @app.route("/api/auth/me")
    def auth_me():
        user_id = session.get("user_id")
        user = None
        if user_id:
            with database_connection() as connection:
                user = connection.execute("SELECT id, name FROM users WHERE id = ?", (user_id,)).fetchone()
            if user is None:
                session.clear()
        return jsonify({"user": user_response(user) if user else None, "csrf_token": csrf_token()})

    @app.route("/api/auth/register", methods=["POST"])
    @limiter.limit("5/minute")
    def auth_register():
        if not request.is_json:
            return json_error(415, "Request content type must be application/json.")
        if not csrf_is_valid():
            return json_error(400, "Refresh the page and try again.")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return json_error(400, "Invalid account details.")
        name = payload.get("name")
        password = payload.get("password")
        if not isinstance(name, str) or not isinstance(password, str):
            return json_error(400, "Enter a name and password.")
        name = name.strip()
        if not 2 <= len(name) <= 40:
            return json_error(400, "Name must be between 2 and 40 characters.")
        if not 10 <= len(password) <= 128:
            return json_error(400, "Password must be between 10 and 128 characters.")

        salt = secrets.token_bytes(16)
        password_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
        try:
            with database_connection() as connection:
                cursor = connection.execute(
                    "INSERT INTO users (name, salt, password_hash) VALUES (?, ?, ?)",
                    (name, salt.hex(), password_hash.hex()),
                )
                user = connection.execute("SELECT id, name FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
        except sqlite3.IntegrityError:
            return json_error(409, "An account with that name already exists.")

        session.clear()
        session["user_id"] = user["id"]
        token = csrf_token()
        return jsonify({"user": user_response(user), "csrf_token": token}), 201

    @app.route("/api/auth/login", methods=["POST"])
    @limiter.limit("10/minute")
    def auth_login():
        if not request.is_json:
            return json_error(415, "Request content type must be application/json.")
        if not csrf_is_valid():
            return json_error(400, "Refresh the page and try again.")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            return json_error(400, "Invalid account details.")
        name = payload.get("name")
        password = payload.get("password")
        if not isinstance(name, str) or not isinstance(password, str):
            return json_error(400, "Enter your name and password.")
        with database_connection() as connection:
            user = connection.execute(
                "SELECT id, name, salt, password_hash FROM users WHERE name = ? COLLATE NOCASE",
                (name.strip(),),
            ).fetchone()
        if user is None:
            return json_error(401, "Name or password is incorrect.")
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(user["salt"]), PASSWORD_ITERATIONS)
        if not hmac.compare_digest(candidate.hex(), user["password_hash"]):
            return json_error(401, "Name or password is incorrect.")

        session.clear()
        session["user_id"] = user["id"]
        token = csrf_token()
        return jsonify({"user": user_response(user), "csrf_token": token})

    @app.route("/api/auth/logout", methods=["POST"])
    def auth_logout():
        if not csrf_is_valid():
            return json_error(400, "Refresh the page and try again.")
        session.clear()
        return jsonify({"user": None, "csrf_token": csrf_token()})

    @app.route("/api/enhance", methods=["POST"])
    @limiter.limit("10/minute")
    def api_enhance():
        if not session.get("user_id"):
            return json_error(401, "Sign in to enhance prompts.")
        if not csrf_is_valid():
            return json_error(400, "Refresh the page and try again.")
        if not request.is_json:
            return json_error(415, "Request content type must be application/json.")
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get("prompt"), str):
            return json_error(400, "Enter a prompt to enhance.")
        prompt = payload["prompt"].strip()
        if not prompt or len(prompt) > 10_000:
            return json_error(400, "Prompt must contain between 1 and 10,000 characters.")

        current_config = AppConfig()
        if not current_config.api_key:
            return json_error(503, "OpenRouter API is not configured. Add OPENROUTER_API_KEY to your environment.")
        model = payload.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            return json_error(400, "The model must be a non-empty string or null.")

        client = openrouter_client
        model_data = client.get_public_models()
        available_ids = {item.get("id") for item in model_data.get("models", []) if isinstance(item, dict)}
        selected_model = model.strip() if isinstance(model, str) else current_config.default_model
        if selected_model not in available_ids:
            if isinstance(model, str):
                return json_error(400, "That model is unavailable or not free for text chat. Choose a current free model in Settings.")
            selected_model = model_data.get("default")
        if selected_model not in available_ids:
            selected_model = next((item.get("id") for item in model_data.get("models", []) if item.get("id") in available_ids), None)
        if not selected_model:
            return json_error(503, "No free text-chat models are currently available. Try again later.")
        try:
            enhanced = client.enhance_prompt(prompt, selected_model)
        except requests.Timeout:
            return json_error(504, "Prompt enhancement timed out. Try again.")
        except requests.RequestException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status == 429:
                return json_error(429, "The model is rate limited right now. Try again shortly.")
            return json_error(502, "The model could not enhance this prompt. Check the model and try again.")
        except (RuntimeError, ValueError):
            return json_error(502, "The model returned no usable enhanced prompt. Try again.")
        return jsonify({"prompt": enhanced})

    @app.route("/api/chat", methods=["POST"])
    @limiter.limit("30/minute")
    def api_chat():
        if not session.get("user_id"):
            return json_error(401, "Sign in to start chatting.")
        if not request.is_json:
            return json_error(415, "Request content type must be application/json.")

        raw = request.get_data(cache=True, as_text=False)
        if len(raw) > MAX_BODY_BYTES:
            return json_error(413, "Request body exceeds the 200 KB limit.")

        try:
            payload = request.get_json(force=False, silent=False)
        except Exception:
            return json_error(415, "Invalid JSON request body.")

        if not isinstance(payload, dict):
            return json_error(400, "JSON body must be an object.")

        current_config = AppConfig()
        if not current_config.api_key:
            return json_error(503, "OpenRouter API is not configured. Add OPENROUTER_API_KEY to your environment.")

        messages = payload.get("messages")
        if not isinstance(messages, list):
            return json_error(400, "The 'messages' field is required.")
        if not 1 <= len(messages) <= MAX_MESSAGE_COUNT:
            return json_error(400, "Between 1 and 60 messages are allowed.")

        sanitized_messages = []
        for index, message in enumerate(messages):
            if not isinstance(message, dict):
                return json_error(400, f"Message at index {index} must be an object.")
            role = message.get("role")
            content = message.get("content")
            if role not in ALLOWED_ROLES:
                return json_error(400, f"Message at index {index} has an invalid role.")
            if not isinstance(content, str):
                return json_error(400, f"Message at index {index} must contain a string content field.")
            if len(content) > MAX_MESSAGE_CHARS:
                return json_error(413, f"Message at index {index} exceeds 20,000 characters.")
            sanitized_messages.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})

        model = payload.get("model")
        if model is not None and (not isinstance(model, str) or not model.strip()):
            return json_error(400, "The 'model' field must be a non-empty string or null.")

        try:
            temperature = float(payload.get("temperature", 0.7))
        except (TypeError, ValueError):
            return json_error(400, "Temperature must be a number between 0 and 2.")
        if not 0.0 <= temperature <= 2.0:
            return json_error(400, "Temperature must be between 0 and 2.")

        try:
            max_tokens = int(payload.get("max_tokens", MAX_COMPLETION_TOKENS))
        except (TypeError, ValueError):
            return json_error(400, "Max tokens must be an integer between 1 and 8192.")
        if not 1 <= max_tokens <= 8192:
            return json_error(400, "Max tokens must be between 1 and 8192.")

        client = openrouter_client
        model_data = client.get_public_models()
        available_ids = {item.get("id") for item in model_data.get("models", []) if isinstance(item, dict)}
        selected_model = model.strip() if isinstance(model, str) else current_config.default_model
        if selected_model not in available_ids:
            if isinstance(model, str):
                return json_error(400, "That model is unavailable or not free for text chat. Choose a current free model in Settings.")
            selected_model = model_data.get("default")
        if selected_model not in available_ids:
            selected_model = next((item.get("id") for item in model_data.get("models", []) if item.get("id") in available_ids), None)
        if not selected_model:
            return json_error(503, "No free text-chat models are currently available. Try again later.")
        free_fallback_models = [model_id for model_id in current_config.fallback_models if model_id in available_ids]

        def event_stream():
            yield "event: meta\ndata: {\"model\": \"%s\", \"fallback_used\": false}\n\n" % (selected_model or current_config.default_model)
            try:
                for item in client.stream_chat(
                    messages=sanitized_messages,
                    model=selected_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    fallback_models=free_fallback_models,
                ):
                    if isinstance(item, dict):
                        event_name = item.get("event")
                        payload_obj = {k: v for k, v in item.items() if k != "event"}
                        yield f"event: {event_name}\ndata: {json.dumps(payload_obj, separators=(',', ':'))}\n\n"
                    else:
                        yield item
            except RuntimeError as exc:
                yield f"event: error\ndata: {json.dumps({'code': 'service_unavailable', 'message': str(exc)})}\n\n"
            except Exception as exc:
                yield f"event: error\ndata: {json.dumps({'code': 'internal_error', 'message': 'The request could not be completed. Please try again.'})}\n\n"

        return Response(stream_with_context(event_stream()), mimetype="text/event-stream")

    @app.route("/health")
    def health():
        current_config = AppConfig()
        payload = {
            "status": "ok",
            "api_key_configured": bool(current_config.api_key),
            "default_model": current_config.default_model,
            "version": APP_VERSION,
        }
        return jsonify(payload)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=False)
