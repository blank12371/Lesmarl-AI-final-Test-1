# Lesmarl AI

Made by Mashrur Ahmed Arib.

Lesmarl AI is a premium AI chat product built as a polished Flask app with a static HTML, CSS, and vanilla JavaScript frontend. It connects securely to OpenRouter, supports streaming replies, exposes a modern model switcher, and ships with testing and Render deployment guidance.

## Overview

- Streaming chat with model failover and retry handling
- Free model discovery and default model recommendation
- Dark and light themes with accent selection
- Markdown rendering, code blocks, attachments, export, and chat management
- Local conversation storage with graceful fallback
- Security-focused headers and safe rendering of model output

## Architecture

```text
Browser -> Flask app -> OpenRouter API
        |              |
        |              +-> model list cache (10 minutes)
        |              +-> failover router
        +-> SSE stream to the UI
``` 

## Project layout

```text
lesmarl-ai/
├── app.py
├── config.py
├── openrouter_client.py
├── templates/
│   ├── index.html
│   ├── about.html
│   ├── privacy.html
│   └── license.html
├── static/css/
│   ├── tokens.css
│   ├── base.css
│   └── components.css
├── static/js/
│   ├── app.js
│   ├── chat.js
│   ├── markdown.js
│   ├── highlight.js
│   ├── storage.js
│   ├── ui.js
│   └── i18n.js
├── tests/
│   ├── test_api.py
│   ├── test_validation.py
│   └── test_markdown_cases.md
├── render.yaml
├── Procfile
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
├── humans.txt
├── robots.txt
└── .well-known/security.txt
```

## Local setup

```bash
cd lesmarl-ai
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# set OPENROUTER_API_KEY in .env
python app.py
```

Then visit http://localhost:5000.

## OpenRouter and free model setup

1. Create an OpenRouter account and generate a key.
2. Add the key to your environment or .env file.
3. Set `DEFAULT_MODEL` and `FALLBACK_MODELS` to free model IDs ending in `:free`.
4. Free models can change and may rate-limit; check the model list at `/api/models`.

## Environment variables

| Name | Description | Example |
| --- | --- | --- |
| OPENROUTER_API_KEY | Secret API key from OpenRouter | `sk-or-...` |
| DEFAULT_MODEL | Preferred free model | `meta-llama/llama-3.1-8b-instruct:free` |
| FALLBACK_MODELS | Comma-separated fallback models | `google/gemma-3-4b-it:free,mistralai/mistral-7b-instruct:free` |
| SITE_URL | Public URL used as HTTP-Referer | `https://example.com` |
| PORT | Flask port for local runs | `5000` |
| PYTHON_VERSION | Runtime version | `3.11` |
| RATE_LIMIT | Request rate limit | `60/minute` |

## API reference

### POST /api/chat

Request JSON example:

```json
{
  "model": "meta-llama/llama-3.1-8b-instruct:free",
  "messages": [
    {"role": "user", "content": "Explain the project in plain language."}
  ],
  "temperature": 0.7,
  "max_tokens": 512
}
```

The endpoint returns an SSE stream with:

- `meta` with model and fallback state
- `token` text chunks
- `done` metadata and usage
- `error` with a code and message

### GET /api/models

Returns JSON like:

```json
{
  "models": [
    {"id": "meta-llama/llama-3.1-8b-instruct:free", "name": "Llama 3.1 8B", "context_length": 128000, "description": "Free model"}
  ],
  "default": "meta-llama/llama-3.1-8b-instruct:free",
  "cached_at": "2026-11-02T00:00:00+00:00"
}
```

### GET /health

Returns runtime health details without exposing secrets.

### Common error codes

- `400` invalid payload
- `413` oversized request or message
- `415` wrong content type or invalid JSON
- `429` rate limit reached
- `502` upstream gateway failure
- `503` API key or service unavailable
- `504` upstream timeout

## Render deployment blueprint

Use the following values in Render:

- Root Directory: leave blank
- Build Command: `pip install -r requirements.txt`
- Start Command: `gunicorn app:app --worker-class gthread --workers 1 --threads 8 --timeout 120`
- Health Check Path: `/health`
- Keep secrets only in the Render dashboard, never in version control

Note: free Render instances may sleep while idle, and free OpenRouter models have limited daily usage.

## Running the tests

```bash
pytest -q
```

## Security notes

- The app uses same-origin static files and a strict Content Security Policy.
- Model output is escaped before rendering.
- Use HTTPS in production and keep the code readable and unobfuscated.
- The project is MIT-licensed and dependencies maintain their own licenses.

## If your site is flagged

1. Request a review in Google Search Console and Safe Browsing.
2. Submit a false-positive report to the flagging vendor.
3. Use a custom domain with HTTPS.
4. Keep the source code clear, readable, and unobfuscated.
5. Confirm no hidden iframes, redirects, or scripts are present.

## License

This project is released under the MIT License.

Copyright (c) 2026 Mashrur Ahmed Arib

People may use and modify it freely, but they must keep the LICENSE and copyright notice. The software is provided as is, with no warranty, and AI output may be wrong. Third-party dependencies keep their own licenses.

## Credits

Made by Mashrur Ahmed Arib.
