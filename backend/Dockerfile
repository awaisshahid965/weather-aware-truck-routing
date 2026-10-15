# syntax=docker/dockerfile:1

# --- Build: resolve the locked runtime dependencies into a virtualenv ---------------
FROM python:3.14.8-slim AS build

COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

# --- Runtime: the virtualenv plus the source, run as an unprivileged user ------------------
FROM python:3.14.8-slim AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --system app && useradd --system --gid app --no-create-home app

WORKDIR /app
COPY --from=build /opt/venv /opt/venv
COPY . .

USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import os, urllib.request; urllib.request.urlopen(f\"http://127.0.0.1:{os.environ.get('PORT', '8000')}/healthz\", timeout=2)"]

# Refuse to start with unsafe production settings, then hand PID 1 to gunicorn.
CMD ["sh", "-c", "python manage.py check --deploy --fail-level WARNING && exec gunicorn config.wsgi"]
