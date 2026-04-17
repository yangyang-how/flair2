# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv — fast, deterministic installs from uv.lock
COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /usr/local/bin/

# Copy manifest + lockfile first (layer cache); dev extras included so tests
# can run in the image too.
COPY pyproject.toml uv.lock ./

# Install into a self-contained venv at /app/venv. --frozen fails if the
# lockfile is out of sync with pyproject.toml — the whole point of checking
# in uv.lock.
ENV UV_PROJECT_ENVIRONMENT=/app/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN uv sync --frozen --no-install-project --extra dev

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# curl for ECS container health check + non-root user
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --no-create-home --shell /bin/false appuser

# Copy venv from builder
COPY --from=builder /app/venv /app/venv

# Copy application code, tests, pytest config, and dataset
COPY pyproject.toml uv.lock ./
COPY app/ ./app/
COPY tests/ ./tests/
COPY data/ ./data/

# Use venv python
ENV PATH="/app/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

# API service default CMD
# Celery worker overrides this in ECS task definition:
#   celery -A app.worker worker --loglevel=info --concurrency=4
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
