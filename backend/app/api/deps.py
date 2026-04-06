"""Dependency injection for FastAPI routes.

Provides Redis, Orchestrator, and Provider instances via Depends().
Stubs are used until Jess's infra clients (#73) are merged.

Contract: https://github.com/yangyang-how/flair2/issues/71 Section 6.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
import structlog

from app.config import settings

logger = structlog.get_logger()

# ── Redis connection pool (singleton) ───────────────────────

_redis_pool: aioredis.Redis | None = None


async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    """Yield an async Redis connection from the shared pool.

    Uses db=0 (state). Celery uses db=1 (broker) — never mix them.
    """
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    yield _redis_pool


async def close_redis() -> None:
    """Close the Redis pool on app shutdown."""
    global _redis_pool
    if _redis_pool is not None:
        await _redis_pool.aclose()
        _redis_pool = None


# ── Session ID (from cookie or header) ──────────────────────

SESSION_HEADER = "X-Session-ID"


def get_session_id(session_id: str | None = None) -> str:
    """Extract session ID from query param.

    In production this would come from a cookie or auth header.
    For now, the frontend sends it as a query parameter.
    """
    return session_id or "anonymous"
