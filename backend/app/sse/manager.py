"""SSE event manager — streams pipeline events via Redis Streams.

Uses XREAD (not BLPOP) so multiple browser tabs on the same run_id
each receive every event independently. Each connection maintains
its own cursor.

Contract: https://github.com/yangyang-how/flair2/issues/71 Section 2.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import redis.asyncio as aioredis
import structlog
from fastapi import Request
from sse_starlette.sse import ServerSentEvent

from app.models.pipeline import PipelineStatus

logger = structlog.get_logger()

# Stream key pattern — one stream per pipeline run
STREAM_KEY = "sse:{run_id}"

# How long to block on XREAD before checking if client disconnected (ms)
XREAD_BLOCK_MS = 5000

# Max events to read per XREAD call
XREAD_COUNT = 10

# Terminal pipeline states — stop streaming after these
_TERMINAL_STATUSES = {PipelineStatus.COMPLETED, PipelineStatus.FAILED}


async def sse_event_generator(
    redis: aioredis.Redis,
    run_id: str,
    cursor: str,
    request: Request,
) -> AsyncGenerator[ServerSentEvent | dict, None]:
    """Yield SSE events from the Redis Stream for a pipeline run.

    Args:
        redis: Async Redis connection.
        run_id: Pipeline run ID.
        cursor: Redis Stream message ID to resume from.
            "0-0" for new connections (read from beginning).
            A specific ID for reconnects (from Last-Event-ID).
        request: FastAPI request — used to detect client disconnect.

    Yields:
        ServerSentEvent dicts compatible with sse-starlette.
    """
    stream_key = STREAM_KEY.format(run_id=run_id)
    last_id = cursor

    logger.info("sse_connection_opened", run_id=run_id, cursor=cursor)

    try:
        while True:
            # Check if the client disconnected
            if await request.is_disconnected():
                logger.info("sse_client_disconnected", run_id=run_id)
                break

            # XREAD — blocks up to XREAD_BLOCK_MS, then loops to check disconnect
            try:
                entries = await redis.xread(
                    {stream_key: last_id},
                    block=XREAD_BLOCK_MS,
                    count=XREAD_COUNT,
                )
            except aioredis.ConnectionError:
                logger.warning("sse_redis_connection_lost", run_id=run_id)
                # Use contract-aligned pipeline_error event shape
                yield ServerSentEvent(
                    data=json.dumps(
                        {
                            "event": "pipeline_error",
                            "data": {
                                "stage": "unknown",
                                "error": "Redis connection lost",
                                "recoverable": True,
                            },
                        }
                    ),
                    event="pipeline_error",
                )
                break

            if not entries:
                # No new events — check if pipeline is in a terminal state
                status = await redis.get(f"run:{run_id}:status")
                if status in _TERMINAL_STATUSES:
                    logger.info(
                        "sse_pipeline_terminal",
                        run_id=run_id,
                        status=status,
                    )
                    break
                # Otherwise loop — keep waiting for events
                continue

            # Process received events
            for _stream_name, messages in entries:
                for msg_id, fields in messages:
                    payload = fields.get("payload", "{}")
                    last_id = msg_id

                    try:
                        event_data = json.loads(payload)
                    except json.JSONDecodeError:
                        logger.warning(
                            "sse_malformed_event",
                            run_id=run_id,
                            msg_id=msg_id,
                            payload=payload[:200],
                        )
                        continue  # Skip bad events, don't kill the stream

                    yield ServerSentEvent(
                        id=msg_id,
                        event=event_data.get("event", "message"),
                        data=payload,
                    )

                    # If this is a terminal event, stop after yielding it
                    event_type = event_data.get("event")
                    if event_type in ("pipeline_complete", "pipeline_error"):
                        logger.info(
                            "sse_terminal_event",
                            run_id=run_id,
                            event_type=event_type,
                        )
                        return

    finally:
        logger.info("sse_connection_closed", run_id=run_id, last_id=last_id)
