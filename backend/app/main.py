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

# CORS — allow frontend origins in dev
# Astro dev server (4321) and fallback (3000) in debug mode
_DEV_ORIGINS = ["http://localhost:4321", "http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEV_ORIGINS if settings.debug else [],
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
