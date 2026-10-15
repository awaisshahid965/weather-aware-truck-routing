# Backend

Django REST API for weather-aware truck routing. It is stateless: no database.

## Requirements

- [uv](https://docs.astral.sh/uv/) 0.13.1 or newer. uv installs Python 3.14.8 from `.python-version`.

## First run

```bash
cd backend
uv sync                  # creates .venv with Python 3.14.8 and all dependencies
cp .env.example .env     # local settings: DEBUG on, CORS open to http://localhost:3000
uv run poe dev           # http://localhost:8000
```

Check it: `curl http://localhost:8000/healthz` returns `{"status": "ok"}`.

## Commands

| Command | What it does |
|---|---|
| `uv run poe dev` | Development server on port 8000, with `.env` loaded |
| `uv run poe check` | Everything CI runs: format check, lint, layer contracts, types, tests |
| `uv run poe format` | Format all files |
| `uv run poe lint` | Ruff lint plus import-linter layer contracts |
| `uv run poe lint:fix` | Apply safe lint fixes |
| `uv run poe typecheck` | mypy, strict |
| `uv run poe test` | pytest, without live provider tests |
| `uv run poe test:live` | Only tests marked `live`, which call real provider APIs (needs keys in `.env`) |
| `uv run poe check:deploy` | Django deployment checks against the current environment |

Run `uv run poe` with no task to list them all. Pass extra arguments after the task: `uv run poe test -k health`.

## Layout

```text
config/      Django project: settings, env parsing, URLs, WSGI, health probe, JSON logging
routing/     The application, in layers: domain, ports, services, adapters, http
tests/       pytest suite, mirroring the package layout
```

How the layers depend on each other, and every coding rule: [CONVENTIONS.md](CONVENTIONS.md).

## Configuration

All settings come from environment variables. Locally they come from `.env`; see `.env.example`.

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | `false` | Debug mode. Only for local development. |
| `DJANGO_SECRET_KEY` | insecure development key | Required in production. At least 50 random characters. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,[::1]` | Host names the API answers to |
| `CORS_ALLOWED_ORIGINS` | empty | Browser origins allowed to call the API, e.g. the frontend URL |
| `DJANGO_SECURE_SSL_REDIRECT` | on when not debugging | Redirect HTTP to HTTPS |
| `DJANGO_SECURE_HSTS_SECONDS` | `3600` when not debugging | HSTS max-age |
| `DJANGO_TRUST_X_FORWARDED_PROTO` | `false` | Trust the proxy's `X-Forwarded-Proto` header. Turn on behind a TLS-terminating proxy. |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, or `ERROR` |
| `LOG_FORMAT` | `json`, or `text` when debugging | `json` (one object per line) or `text` |
| `HERE_API_KEY` | empty | HERE routing and geocoding API key |
| `PORT` | `8000` | Port gunicorn listens on (container) |
| `WEB_CONCURRENCY` | `2` | Gunicorn worker processes (container) |

## Production

Build and run the image:

```bash
docker build -t truck-routing-backend .
docker run --rm -p 8000:8000 \
  -e DJANGO_SECRET_KEY="<50+ random characters>" \
  -e DJANGO_ALLOWED_HOSTS=api.example.com \
  -e CORS_ALLOWED_ORIGINS=https://app.example.com \
  -e DJANGO_TRUST_X_FORWARDED_PROTO=true \
  -e HERE_API_KEY="<key>" \
  truck-routing-backend
```

- The container runs `manage.py check --deploy` before it serves. Unsafe settings stop it at startup.
- The liveness probe is `GET /healthz`. It answers over plain HTTP, for any host.
- Logs are JSON lines on stdout and stderr.
