"""Pipeline endpoints: start, status (SSE), results.

Contract: https://github.com/yangyang-how/flair2/issues/71
"""

from __future__ import annotations

import json
import uuid

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sse_starlette.sse import EventSourceResponse

from app.api.deps import get_redis, get_session_id
from app.models.api import (
    RunListResponse,
    RunStatusResponse,
    StartPipelineRequest,
    StartPipelineResponse,
)
from app.models.pipeline import PipelineConfig, PipelineStatus
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

    Creates run state in Redis, enqueues S1 tasks via the orchestrator.
    Orchestrator integration is stubbed until Jess's track (#73) merges.
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

    # Store run config and initial state in Redis
    pipeline = r.pipeline()
    pipeline.set(f"run:{run_id}:config", config.model_dump_json())
    pipeline.set(f"run:{run_id}:status", PipelineStatus.PENDING)
    pipeline.set(f"run:{run_id}:stage", "PENDING")
    pipeline.rpush(f"session:{session_id}:runs", run_id)
    await pipeline.execute()

    logger.info(
        "pipeline_created",
        run_id=run_id,
        session_id=session_id,
        reasoning_model=req.reasoning_model,
        num_videos=req.num_videos,
        num_personas=req.num_personas,
        top_n=req.top_n,
    )

    # TODO: call orchestrator.start(config, videos) once #73 merges
    # For now, the run sits in PENDING until the orchestrator is wired up.

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
