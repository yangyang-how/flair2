"""Unit tests for Orchestrator state machine using fakeredis.

Task dispatch is mocked so these tests run without a real Celery broker.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from app.infra.redis_client import RedisClient
from app.models.pipeline import CreatorProfile, PipelineConfig
from app.models.stages import (
    CandidateScript,
    FinalResult,
    RankedScript,
    S5Rankings,
    VideoInput,
)
from app.pipeline.orchestrator import Orchestrator


@pytest_asyncio.fixture
async def redis():
    fake = fake_aioredis.FakeRedis(decode_responses=True)
    client = RedisClient.__new__(RedisClient)
    client._redis = fake
    yield client
    await fake.aclose()


@pytest.fixture
def config():
    return PipelineConfig(
        run_id="test-run",
        session_id="sess1",
        reasoning_model="kimi",
        creator_profile=CreatorProfile(
            tone="casual",
            vocabulary=[],
            catchphrases=[],
            topics_to_avoid=[],
        ),
        num_videos=3,
        num_scripts=5,
        num_personas=2,
        top_n=2,
    )


@pytest.fixture
def videos():
    return [
        VideoInput(
            video_id=f"v{i}", transcript=None, description=None, duration=30.0, engagement={}
        )
        for i in range(3)
    ]


def _read_stream_events(redis_client, run_id: str) -> list[dict]:
    """Synchronously read all SSE events from stream using raw fakeredis."""
    import asyncio
    async def _read():
        entries = await redis_client._redis.xread({f"sse:{run_id}": "0-0"}, count=100)
        events = []
        if entries:
            for _stream, messages in entries:
                for _id, fields in messages:
                    payload = json.loads(fields.get("payload", "{}"))
                    events.append({
                        "event": payload.get("event"),
                        "data": payload.get("data", {}),
                    })
        return events
    return asyncio.get_event_loop().run_until_complete(_read())


# ---------------------------------------------------------------------------
# start()
# ---------------------------------------------------------------------------

async def test_start_initializes_counters(redis, config, videos):
    with patch("app.workers.tasks.s1_analyze_task") as mock_task:
        mock_task.delay = MagicMock()
        orch = Orchestrator(redis)
        await orch.start("test-run", config, videos)

    assert await redis.get("run:test-run:s1:done") == "0"
    assert await redis.get("run:test-run:s4:done") == "0"
    assert await redis.get("run:test-run:s6:done") == "0"
    assert await redis.get("run:test-run:stage") == "S1_MAP"
    assert await redis.get("run:test-run:status") == "running"


async def test_start_dispatches_s1_tasks(redis, config, videos):
    with patch("app.workers.tasks.s1_analyze_task") as mock_task:
        mock_task.delay = MagicMock()
        await Orchestrator(redis).start("test-run", config, videos)

    assert mock_task.delay.call_count == 3


async def test_start_emits_pipeline_started_event(redis, config, videos):
    with patch("app.workers.tasks.s1_analyze_task") as mock_task:
        mock_task.delay = MagicMock()
        await Orchestrator(redis).start("test-run", config, videos)

    entries = await redis.xread({"sse:test-run": "0-0"}, block=100, count=10)
    assert entries
    event_types = [
        json.loads(fields["payload"])["event"]
        for _stream, msgs in entries
        for _id, fields in msgs
    ]
    assert "pipeline_started" in event_types
    assert "stage_started" in event_types


# ---------------------------------------------------------------------------
# S1 → S2 transition
# ---------------------------------------------------------------------------

async def test_on_s1_complete_increments_counter(redis, config, videos):
    with patch("app.workers.tasks.s1_analyze_task") as mock_task:
        mock_task.delay = MagicMock()
        await Orchestrator(redis).start("test-run", config, videos)

    with patch("app.workers.tasks.s2_aggregate_task") as mock_s2:
        mock_s2.delay = MagicMock()
        orch = Orchestrator(redis)
        await orch.on_s1_complete("test-run", "v0")
        assert await redis.get("run:test-run:s1:done") == "1"
        mock_s2.delay.assert_not_called()

        await orch.on_s1_complete("test-run", "v1")
        await orch.on_s1_complete("test-run", "v2")
        # After 3rd completion (== num_videos=3), S2 should be dispatched
        mock_s2.delay.assert_called_once_with("test-run")


async def test_s1_complete_transitions_stage(redis, config, videos):
    with patch("app.workers.tasks.s1_analyze_task") as mock_task:
        mock_task.delay = MagicMock()
        await Orchestrator(redis).start("test-run", config, videos)

    with patch("app.workers.tasks.s2_aggregate_task") as mock_s2:
        mock_s2.delay = MagicMock()
        orch = Orchestrator(redis)
        for i in range(3):
            await orch.on_s1_complete("test-run", f"v{i}")

    assert await redis.get("run:test-run:stage") == "S2_REDUCE"


# ---------------------------------------------------------------------------
# S2 → S3 transition
# ---------------------------------------------------------------------------

async def test_on_s2_complete_dispatches_s3(redis, config):
    await redis.set("run:test-run:config", config.model_dump_json())

    with patch("app.workers.tasks.s3_generate_task") as mock_s3:
        mock_s3.delay = MagicMock()
        await Orchestrator(redis).on_s2_complete("test-run")
        mock_s3.delay.assert_called_once_with("test-run")

    assert await redis.get("run:test-run:stage") == "S3_SEQUENTIAL"


# ---------------------------------------------------------------------------
# S3 → S4 transition
# ---------------------------------------------------------------------------

async def test_on_s3_complete_dispatches_s4(redis, config):
    await redis.set("run:test-run:config", config.model_dump_json())

    with patch("app.workers.tasks.s4_vote_task") as mock_s4:
        mock_s4.delay = MagicMock()
        await Orchestrator(redis).on_s3_complete("test-run")
        assert mock_s4.delay.call_count == config.num_personas

    assert await redis.get("run:test-run:stage") == "S4_MAP"


# ---------------------------------------------------------------------------
# S5 → S6 transition
# ---------------------------------------------------------------------------

async def test_on_s5_complete_dispatches_s6(redis, config):
    await redis.set("run:test-run:config", config.model_dump_json())
    rankings = S5Rankings(
        top_10=[
            RankedScript(script_id="s1", vote_count=5, score=10.0, rank=1),
            RankedScript(script_id="s2", vote_count=4, score=8.0, rank=2),
        ],
        total_votes_cast=2,
    )
    await redis.set("top_scripts:test-run", rankings.model_dump_json())

    with patch("app.workers.tasks.s6_personalize_task") as mock_s6:
        mock_s6.delay = MagicMock()
        await Orchestrator(redis).on_s5_complete("test-run")
        assert mock_s6.delay.call_count == config.top_n


# ---------------------------------------------------------------------------
# Finalize (all S6 complete)
# ---------------------------------------------------------------------------

async def test_finalize_builds_s6_output(redis, config):
    await redis.set("run:test-run:config", config.model_dump_json())

    def _script(sid: str) -> CandidateScript:
        return CandidateScript(
            script_id=sid, pattern_used="p", hook="h", body="b",
            payoff="pay", estimated_duration=30.0, structural_notes="",
        )

    candidates = [_script("s1"), _script("s2")]
    rankings = S5Rankings(
        top_10=[
            RankedScript(script_id="s1", vote_count=5, score=10.0, rank=1),
            RankedScript(script_id="s2", vote_count=4, score=8.0, rank=2),
        ],
        total_votes_cast=2,
    )
    await redis.set("top_scripts:test-run", rankings.model_dump_json())

    for c in candidates:
        result = FinalResult(
            script_id=c.script_id,
            original_script=c,
            personalized_script="p",
            video_prompt="v",
            rank=1,
            vote_score=10.0,
        )
        await redis.set(f"result:s6:test-run:{c.script_id}", result.model_dump_json())

    # Simulate s6 done counter reaching top_n
    await redis.set("run:test-run:s6:done", "1")
    await Orchestrator(redis).on_s6_complete("test-run", "s2")  # this makes it 2

    assert await redis.get("run:test-run:status") == "completed"
    final_raw = await redis.get("results:final:test-run")
    assert final_raw is not None
    from app.models.stages import S6Output
    output = S6Output.model_validate_json(final_raw)
    assert len(output.results) == 2


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

async def test_on_failure_sets_failed_state(redis, config):
    await redis.set("run:test-run:config", config.model_dump_json())
    await Orchestrator(redis).on_failure("test-run", "S1_MAP", "something exploded")

    assert await redis.get("run:test-run:status") == "failed"
    assert await redis.get("run:test-run:stage") == "FAILED"
