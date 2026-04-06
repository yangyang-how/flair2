"""Unit tests for the SSE manager.

Tests XREAD-based event streaming with fakeredis.
"""

import json

import fakeredis.aioredis
import pytest

from app.sse.manager import STREAM_KEY, sse_event_generator


class FakeRequest:
    """Minimal request mock for SSE generator."""

    def __init__(self):
        self._disconnected = False

    async def is_disconnected(self) -> bool:
        return self._disconnected

    def disconnect(self):
        self._disconnected = True

    @property
    def headers(self):
        return {}


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
def fake_request():
    return FakeRequest()


class TestSSEManager:
    async def test_streams_events_from_redis(self, fake_redis, fake_request):
        """Events XADDed to the stream are yielded by the generator."""
        run_id = "test-run"
        stream_key = STREAM_KEY.format(run_id=run_id)

        # Pre-populate stream with events
        event1 = json.dumps({"event": "stage_started", "data": {"stage": "S1_MAP"}})
        event2 = json.dumps({"event": "pipeline_complete", "data": {"run_id": run_id}})

        await fake_redis.xadd(stream_key, {"payload": event1})
        await fake_redis.xadd(stream_key, {"payload": event2})

        # Collect events
        events = []
        gen = sse_event_generator(fake_redis, run_id, "0-0", fake_request)
        async for event in gen:
            events.append(event)

        assert len(events) == 2
        # First event is stage_started
        assert events[0].event == "stage_started"
        # Second event is terminal — generator stops
        assert events[1].event == "pipeline_complete"

    async def test_stops_on_client_disconnect(self, fake_redis, fake_request):
        """Generator exits when client disconnects."""
        run_id = "test-run"

        # Set pipeline as running (not terminal) so it would normally keep going
        await fake_redis.set(f"run:{run_id}:status", "running")

        # Disconnect immediately
        fake_request.disconnect()

        events = []
        gen = sse_event_generator(fake_redis, run_id, "0-0", fake_request)
        async for event in gen:
            events.append(event)

        assert len(events) == 0

    async def test_stops_on_terminal_status(self, fake_redis, fake_request):
        """Generator exits when pipeline reaches terminal state and no new events."""
        run_id = "test-run"

        # Pipeline already completed, no events in stream
        await fake_redis.set(f"run:{run_id}:status", "completed")

        events = []
        gen = sse_event_generator(fake_redis, run_id, "0-0", fake_request)

        # This should terminate after one XREAD timeout cycle
        async for event in gen:
            events.append(event)

        assert len(events) == 0

    async def test_resumes_from_cursor(self, fake_redis, fake_request):
        """Events before the cursor are skipped (reconnect scenario)."""
        run_id = "test-run"
        stream_key = STREAM_KEY.format(run_id=run_id)

        # Add two events, capture the ID of the first
        first_id = await fake_redis.xadd(
            stream_key,
            {"payload": json.dumps({"event": "stage_started", "data": {}})},
        )
        await fake_redis.xadd(
            stream_key,
            {"payload": json.dumps({"event": "pipeline_complete", "data": {"run_id": run_id}})},
        )

        # Resume from after the first event
        events = []
        gen = sse_event_generator(fake_redis, run_id, first_id, fake_request)
        async for event in gen:
            events.append(event)

        # Should only get the second event
        assert len(events) == 1
        assert events[0].event == "pipeline_complete"

    async def test_error_event_stops_stream(self, fake_redis, fake_request):
        """pipeline_error event is a terminal event."""
        run_id = "test-run"
        stream_key = STREAM_KEY.format(run_id=run_id)

        await fake_redis.xadd(
            stream_key,
            {
                "payload": json.dumps(
                    {
                        "event": "pipeline_error",
                        "data": {"stage": "S1_MAP", "error": "boom"},
                    }
                )
            },
        )

        events = []
        gen = sse_event_generator(fake_redis, run_id, "0-0", fake_request)
        async for event in gen:
            events.append(event)

        assert len(events) == 1
        assert events[0].event == "pipeline_error"
