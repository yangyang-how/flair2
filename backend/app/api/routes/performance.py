"""Performance tracking endpoints.

Stores video performance metrics for the feedback loop.
Uses Redis as interim storage until DynamoDB client (#73) is ready.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import redis.asyncio as aioredis
import structlog
from fastapi import APIRouter, Depends

from app.api.deps import get_redis
from app.models.api import SubmitPerformanceRequest

logger = structlog.get_logger()
router = APIRouter(tags=["performance"])


@router.post("/api/performance")
async def submit_performance(
    req: SubmitPerformanceRequest,
    r: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Submit performance metrics for a posted video.

    In production, writes to DynamoDB video_performance table.
    For now, stores in Redis as a temporary shim.
    """
    perf_data = {
        **req.model_dump(),
        "posted_at": datetime.now(UTC).isoformat(),
    }

    # Store indexed by run_id + script_id
    key = f"perf:{req.run_id}:{req.script_id}"
    await r.set(key, json.dumps(perf_data))

    # Also add to the per-run performance list
    await r.rpush(f"perf:list:{req.run_id}", json.dumps(perf_data))

    logger.info(
        "performance_submitted",
        run_id=req.run_id,
        script_id=req.script_id,
        platform=req.platform,
    )

    return {"status": "ok"}


@router.get("/api/performance/{run_id}")
async def get_performance(
    run_id: str,
    r: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Get all performance data for a run's posted videos."""
    raw_list = await r.lrange(f"perf:list:{run_id}", 0, -1)
    results = [json.loads(item) for item in raw_list]
    return {"run_id": run_id, "performances": results}


@router.get("/api/insights")
async def get_insights(
    r: aioredis.Redis = Depends(get_redis),
) -> dict:
    """Aggregated insights across all tracked videos.

    TODO: implement real aggregation once DynamoDB client is available.
    This is a placeholder that returns an empty structure.
    """
    return {
        "top_patterns": [],
        "prediction_accuracy": None,
        "total_videos_tracked": 0,
    }
