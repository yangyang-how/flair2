# ── Build stage ───────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy only dependency manifest first (layer cache)
COPY pyproject.toml .

# Install production deps into /app/venv
RUN python -m venv /app/venv && \
    /app/venv/bin/pip install --upgrade pip && \
    /app/venv/bin/pip install . --no-cache-dir

# ── Runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Non-root user for ECS security best practice
RUN useradd --no-create-home --shell /bin/false appuser

# Copy venv from builder
COPY --from=builder /app/venv /app/venv

# Copy application code
COPY app/ ./app/

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
