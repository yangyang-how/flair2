"""FastAPI application entry point.

Run with: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import close_redis
from app.api.routes import health, performance, pipeline, providers, video
from app.config import settings

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle events."""
    logger.info("app_starting", environment=settings.environment)
    yield
    await close_redis()
    logger.info("app_shutdown")


app = FastAPI(
    title="Flair2 — AI Campaign Studio",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend origins in dev, lock down in production.
# Astro dev server auto-increments port when 4321 is taken, so we
# cover the common range. Production uses same-origin (no CORS needed).
_DEV_ORIGINS = [
    f"http://localhost:{port}"
    for port in [3000, 4321, 4322, 4323, 4324, 5173]
]

_is_dev = settings.environment == "dev"

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS if _is_dev else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register route modules
app.include_router(health.router)
app.include_router(pipeline.router)
app.include_router(video.router)
app.include_router(performance.router)
app.include_router(providers.router)
