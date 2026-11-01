# Lesmarl AI - Made by Mashrur Ahmed Arib - MIT License. See LICENSE.
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line.strip().startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def _parse_bool(value):
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_comma_separated(value):
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class AppConfig:
    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.fallback_models = _parse_comma_separated(os.getenv("FALLBACK_MODELS", ""))
        self.default_model = os.getenv("DEFAULT_MODEL", "").strip()
        if not self.default_model and self.fallback_models:
            self.default_model = self.fallback_models[0]
        if not self.default_model:
            self.default_model = "meta-llama/llama-3.1-8b-instruct:free"
        self.site_url = os.getenv("SITE_URL", "http://localhost:5000").strip() or "http://localhost:5000"
        self.port = int(os.getenv("PORT", "5000"))
        self.rate_limit = os.getenv("RATE_LIMIT", "60/minute").strip() or "60/minute"
        self.python_version = os.getenv("PYTHON_VERSION", "3.11").strip() or "3.11"
        self.app_version = "0.1.0"
        self.debug = _parse_bool(os.getenv("DEBUG"))
        self.api_key_configured = bool(self.api_key)

    @property
    def api_ready(self):
        return bool(self.api_key)


config = AppConfig()
