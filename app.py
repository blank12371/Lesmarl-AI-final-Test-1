# Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE.
import json
import os
from pathlib import Path

from flask import Flask, Response, jsonify, render_template, request, stream_with_context
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

from config import AppConfig
from openrouter_client import OpenRouterClient


APP_VERSION = "0.1.0"
ALLOWED_ROLES = {"system", "user", "assistant"}
MAX_MESSAGE_COUNT = 60
MAX_MESSAGE_CHARS = 20_000
MAX_BODY_BYTES = 200 * 1024


def json_error(code, message, extra=None):
    payload = {"error": {"code": str(code), "message": message}}
    if extra:
        payload["error"].update(extra)
    return jsonify(payload), code


def create_app():
    config = AppConfig()
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = MAX_BODY_BYTES
    app.config["VERSION"] = APP_VERSION
    app.config["DEFAULT_MODEL"] = config.default_model
    app.config["FALLBACK_MODELS"] = config.fallback_models
    app.config["OPENROUTER_API_KEY"] = config.api_key

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
        client = OpenRouterClient(api_key=current_config.api_key, site_url=current_config.site_url)
        response = client.get_public_models()
        default_value = current_config.default_model
        if default_value and response.get("default"):
            response["default"] = response["default"] or default_value
        elif default_value:
            response["default"] = default_value
        return jsonify(response)

    @app.route("/api/chat", methods=["POST"])
    @limiter.limit("30/minute")
    def api_chat():
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
            max_tokens = int(payload.get("max_tokens", 512))
        except (TypeError, ValueError):
            return json_error(400, "Max tokens must be an integer between 1 and 8192.")
        if not 1 <= max_tokens <= 8192:
            return json_error(400, "Max tokens must be between 1 and 8192.")

        selected_model = model.strip() if isinstance(model, str) else current_config.default_model
        client = OpenRouterClient(api_key=current_config.api_key, site_url=current_config.site_url)

        def event_stream():
            yield "event: meta\ndata: {\"model\": \"%s\", \"fallback_used\": false}\n\n" % (selected_model or current_config.default_model)
            try:
                for item in client.stream_chat(
                    messages=sanitized_messages,
                    model=selected_model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    fallback_models=current_config.fallback_models,
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
