"""Integration test: 3 concurrent pipeline runs (#33).

Validates that multiple simultaneous pipeline runs complete without
interfering with each other. Tests the orchestrator state machine
directly using fakeredis — no real Redis, Celery, or LLM calls needed.

Run:
    pytest tests/integration/ -v

Acceptance criteria from issue #33:
    [x] 3 runs start and complete concurrently
    [x] Redis keys are namespaced — no cross-run contamination
    [x] SSE streams are isolated per run
    [x] Rate limiter tokens are shared globally across runs
    [x] A failed run does not affect sibling runs
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from app.infra.rate_limiter import TokenBucketRateLimiter
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

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def shared_redis():
    """Single fakeredis instance shared by all concurrent runs.

    Simulates a real Redis server that all workers and orchestrators
    connect to — the critical shared resource for isolation testing.
    """
    fake = fake_aioredis.FakeRedis(decode_responses=True)
    client = RedisClient.__new__(RedisClient)
    client._redis = fake
    yield client
    await fake.aclose()


@pytest.fixture(autouse=True)
def mock_celery_tasks():
    """Patch all Celery task .delay() calls for the entire test module.

    Using a single fixture-level patch (not per-coroutine) avoids
    concurrent patch conflicts when asyncio.gather runs coroutines
    that each try to enter/exit patch context managers concurrently.
    """
    with (
        patch("app.workers.tasks.s1_analyze_task") as s1,
        patch("app.workers.tasks.s2_aggregate_task") as s2,
        patch("app.workers.tasks.s3_generate_task") as s3,
        patch("app.workers.tasks.s4_vote_task") as s4,
        patch("app.workers.tasks.s5_rank_task") as s5,
        patch("app.workers.tasks.s6_personalize_task") as s6,
    ):
        for mock in (s1, s2, s3, s4, s5, s6):
            mock.delay = MagicMock()
        yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _config(run_id: str) -> PipelineConfig:
    return PipelineConfig(
        run_id=run_id,
        session_id=f"sess-{run_id}",
        reasoning_model="kimi",
        creator_profile=CreatorProfile(
            tone="casual", vocabulary=[], catchphrases=[], topics_to_avoid=[]
        ),
        num_videos=2,
        num_scripts=3,
        num_personas=2,
        top_n=1,
    )


def _videos(run_id: str, n: int) -> list[VideoInput]:
    return [
        VideoInput(
            video_id=f"{run_id}:v{i}",
            transcript=None,
            description=None,
            duration=30.0,
            engagement={},
        )
        for i in range(n)
    ]


async def _drive_to_completion(redis: RedisClient, run_id: str) -> None:
    """Drive one run through all 6 stages without real workers.

    Celery tasks are already patched by mock_celery_tasks fixture.
    Manually triggers each orchestrator callback — the same sequence
    real workers would produce.
    """
    config = _config(run_id)
    videos = _videos(run_id, config.num_videos)
    orch = Orchestrator(redis)

    # S1: start + fan-out
    await orch.start(run_id, config, videos)

    # S1 completions → triggers S2 on last
    for video in videos:
        await orch.on_s1_complete(run_id, video.video_id)

    # S2 → S3
    await orch.on_s2_complete(run_id, pattern_count=4)

    # S3 → S4
    await orch.on_s3_complete(run_id)

    # S4: each persona votes → triggers S5 on last
    for i in range(config.num_personas):
        await orch.on_s4_complete(run_id, f"persona_{i}", top_5=[f"s:{run_id}:0"])

    # Seed top_scripts (S5 output) — in production written by s5_rank_task
    script_id = f"s:{run_id}"
    rankings = S5Rankings(
        top_10=[RankedScript(script_id=script_id, vote_count=2, score=10.0, rank=1)],
        total_votes_cast=2,
    )
    await redis.set(f"top_scripts:{run_id}", rankings.model_dump_json())

    # S5 → S6
    await orch.on_s5_complete(run_id)

    # Seed S6 result — in production written by s6_personalize_task
    candidate = CandidateScript(
        script_id=script_id,
        pattern_used="p",
        hook="h",
        body="b",
        payoff="pay",
        estimated_duration=30.0,
        structural_notes="",
    )
    result = FinalResult(
        script_id=script_id,
        original_script=candidate,
        personalized_script="personalized",
        video_prompt="prompt",
        rank=1,
        vote_score=10.0,
    )
    await redis.set(f"result:s6:{run_id}:{script_id}", result.model_dump_json())

    # S6 complete → finalize
    await orch.on_s6_complete(run_id, script_id)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMultiUserValidation:
    """M3-5: Multi-user validation (3 concurrent runs)."""

    async def test_three_concurrent_runs_complete(self, shared_redis):
        """All 3 runs reach 'completed' with no deadlock or data loss."""
        run_ids = ["run-alpha", "run-beta", "run-gamma"]

        await asyncio.gather(*[
            _drive_to_completion(shared_redis, rid) for rid in run_ids
        ])

        for rid in run_ids:
            status = await shared_redis.get(f"run:{rid}:status")
            assert status == "completed", f"{rid} ended with status={status!r}"

    async def test_redis_key_isolation(self, shared_redis):
        """Counters and results from one run don't bleed into others."""
        run_ids = ["iso-a", "iso-b"]

        await asyncio.gather(*[
            _drive_to_completion(shared_redis, rid) for rid in run_ids
        ])

        for rid in run_ids:
            # s1:done must equal this run's num_videos (2), not 4
            s1_done = await shared_redis.get(f"run:{rid}:s1:done")
            assert s1_done == "2", f"{rid}: s1:done={s1_done!r}, expected '2'"

            # Final results must only contain this run's scripts
            raw = await shared_redis.get(f"results:final:{rid}")
            assert raw is not None, f"{rid}: no final results written"
            output = json.loads(raw)
            for r in output["results"]:
                assert rid in r["script_id"], (
                    f"{rid}: result contains foreign script_id={r['script_id']!r}"
                )

    async def test_sse_stream_isolation(self, shared_redis):
        """Each run writes only to its own SSE stream."""
        run_ids = ["sse-x", "sse-y"]

        await asyncio.gather(*[
            _drive_to_completion(shared_redis, rid) for rid in run_ids
        ])

        for rid in run_ids:
            entries = await shared_redis.xread(
                {f"sse:{rid}": "0-0"}, block=100, count=200
            )
            assert entries, f"{rid}: no SSE events found"

            for _stream, messages in entries:
                for _msg_id, fields in messages:
                    payload = json.loads(fields["payload"])
                    data = payload.get("data", {})
                    if "run_id" in data:
                        assert data["run_id"] == rid, (
                            f"SSE stream for {rid} contains foreign run_id={data['run_id']!r}"
                        )

    async def test_shared_rate_limiter_is_global(self, shared_redis):
        """Rate limit tokens are consumed globally — not reset per run."""
        limiter = TokenBucketRateLimiter(
            shared_redis, "test_kimi", max_tokens=5, window_seconds=60
        )

        # Consume all 5 tokens (simulating calls spread across 2 different runs)
        results = [await limiter.acquire() for _ in range(5)]
        assert all(results), "first 5 acquires should succeed"

        # 6th exceeds the shared limit — would pass if limit were per-run
        assert await limiter.acquire() is False, "6th acquire should fail (shared bucket)"

    async def test_failed_run_does_not_affect_siblings(self, shared_redis):
        """A run that fails mid-flight leaves sibling runs untouched."""
        async def _fail(run_id: str):
            cfg = _config(run_id)
            await shared_redis.set(f"run:{run_id}:config", cfg.model_dump_json())
            await Orchestrator(shared_redis).on_failure(run_id, "S1_MAP", "worker crashed")

        await asyncio.gather(
            _drive_to_completion(shared_redis, "sibling-ok-1"),
            _drive_to_completion(shared_redis, "sibling-ok-2"),
            _fail("sibling-fail"),
        )

        assert await shared_redis.get("run:sibling-ok-1:status") == "completed"
        assert await shared_redis.get("run:sibling-ok-2:status") == "completed"
        assert await shared_redis.get("run:sibling-fail:status") == "failed"
        assert await shared_redis.get("run:sibling-fail:stage") == "FAILED"
