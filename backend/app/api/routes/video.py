"""Video generation endpoints.

Video generation is user-triggered and runs on Lambda (S7).
These endpoints are stubs until Lambda integration is wired up.
"""

from __future__ import annotations

import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_redis
from app.models.api import (
    GenerateVideoRequest,
    GenerateVideoResponse,
    VideoStatusResponse,
)

logger = structlog.get_logger()
router = APIRouter(tags=["video"])


@router.post("/api/video/generate")
async def generate_video(
    req: GenerateVideoRequest,
    r: aioredis.Redis = Depends(get_redis),
) -> GenerateVideoResponse:
    """Trigger video generation for a specific script.

    Invokes Lambda with the script's video prompt.
    Stub until Lambda integration is ready.
    """
    # Verify run exists and is completed
    status = await r.get(f"run:{req.run_id}:status")
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run {req.run_id} not found")
    if status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"Run {req.run_id} is {status}, not completed",
        )

    job_id = str(uuid.uuid4())

    # TODO: invoke Lambda with video prompt from results:final:{run_id}
    # For now, store a placeholder status
    await r.set(
        f"results:video:{req.run_id}:{job_id}",
        '{"status": "processing", "video_url": null, "error": null}',
    )

    logger.info(
        "video_generation_started",
        run_id=req.run_id,
        script_id=req.script_id,
        job_id=job_id,
    )

    return GenerateVideoResponse(job_id=job_id)


@router.get("/api/video/status/{run_id}/{job_id}")
async def video_status(
    run_id: str,
    job_id: str,
    r: aioredis.Redis = Depends(get_redis),
) -> VideoStatusResponse:
    """Poll video generation status."""
    raw = await r.get(f"results:video:{run_id}:{job_id}")
    if raw is None:
        raise HTTPException(status_code=404, detail=f"Video job {job_id} not found")

    import json

    data = json.loads(raw)
    return VideoStatusResponse(
        job_id=job_id,
        status=data["status"],
        video_url=data.get("video_url"),
        error=data.get("error"),
    )
