"""Pipeline endpoints: start, status (SSE), results.

Contract: https://github.com/yangyang-how/flair2/issues/71
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_redis, get_session_id
from app.config import settings
from app.infra.redis_client import RedisClient
from app.models.api import (
    RunListResponse,
    RunStatusResponse,
    StartPipelineRequest,
    StartPipelineResponse,
)
from app.models.pipeline import PipelineConfig, PipelineStatus
from app.pipeline.orchestrator import Orchestrator
from app.runner.data_loader import load_videos_from_json
from app.sse.manager import sse_event_generator

logger = structlog.get_logger()
router = APIRouter(tags=["pipeline"])


@router.post("/api/pipeline/start")
async def start_pipeline(
    req: StartPipelineRequest,
    r: aioredis.Redis = Depends(get_redis),
    session_id: str = Depends(get_session_id),
) -> StartPipelineResponse:
    """Start a new pipeline run.

    Loads the video dataset, creates the PipelineConfig, and hands off
    to the Orchestrator which writes run state to Redis and dispatches
    S1 fan-out tasks via Celery.
    """
    run_id = str(uuid.uuid4())

    config = PipelineConfig(
        run_id=run_id,
        session_id=session_id,
        reasoning_model=req.reasoning_model,
        video_model=req.video_model,
        creator_profile=req.creator_profile,
        num_videos=req.num_videos,
        num_scripts=req.num_scripts,
        num_personas=req.num_personas,
        top_n=req.top_n,
    )

    # Load video dataset (local file for now — S3 in production)
    dataset_path = Path(settings.dataset_path)
    if not dataset_path.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Dataset not found at {dataset_path}",
        )
    videos = load_videos_from_json(dataset_path, limit=req.num_videos)

    # Track this run in the session list
    await r.rpush(f"session:{session_id}:runs", run_id)

    # Orchestrator writes config/status/stage to Redis and dispatches S1 tasks
    redis_client = RedisClient(settings.redis_url)
    try:
        orchestrator = Orchestrator(redis_client)
        await orchestrator.start(run_id, config, videos)
    finally:
        await redis_client.aclose()

    logger.info(
        "pipeline_started",
        run_id=run_id,
        session_id=session_id,
        reasoning_model=req.reasoning_model,
        num_videos=len(videos),
        num_personas=req.num_personas,
        top_n=req.top_n,
    )

    return StartPipelineResponse(run_id=run_id)


@router.get("/api/pipeline/status/{run_id}")
async def pipeline_status(
    run_id: str,
    request: Request,
    r: aioredis.Redis = Depends(get_redis),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    """Stream pipeline events via SSE.

    Uses Redis Streams (XREAD) — multi-tab safe. Each connection
    maintains its own cursor. On reconnect, the browser sends
    Last-Event-ID as a header automatically.
    """
    # Verify run exists
    status = await r.get(f"run:{run_id}:status")
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    cursor = last_event_id or "0-0"

    return EventSourceResponse(
        sse_event_generator(r, run_id, cursor, request),
    )


@router.get("/api/pipeline/results/{run_id}")
async def pipeline_results(
    run_id: str,
    r: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Get final pipeline results.

    Reads from Redis (results:final:{run_id}). In production,
    falls back to S3/DynamoDB if Redis key has expired.
    """
    status = await r.get(f"run:{run_id}:status")
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if status != PipelineStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} is {status}, not completed",
        )

    results_json = await r.get(f"results:final:{run_id}")
    if results_json is None:
        raise HTTPException(
            status_code=404,
            detail=f"Results for {run_id} not found in Redis (may have expired)",
        )

    return json.loads(results_json)


@router.get("/api/runs")
async def list_runs(
    r: aioredis.Redis = Depends(get_redis),
    session_id: str = Depends(get_session_id),
) -> RunListResponse:
    """List all pipeline runs for the current session."""
    run_ids = await r.lrange(f"session:{session_id}:runs", 0, -1)

    runs = []
    for rid in run_ids:
        status = await r.get(f"run:{rid}:status")
        stage = await r.get(f"run:{rid}:stage")
        if status is not None:
            runs.append(
                RunStatusResponse(
                    run_id=rid,
                    status=status,
                    current_stage=stage,
                    stages={},  # TODO: populate per-stage status from Redis
                )
            )

    return RunListResponse(runs=runs)
