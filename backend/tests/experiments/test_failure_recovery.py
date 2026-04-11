"""M5-2: Failure recovery + run isolation.

Validates two properties of the checkpoint-recovery mechanism:

1. API-call savings
   A run that crashes mid-S4 and resumes from checkpoint should issue
   significantly fewer LLM calls than a full cold restart.
   Acceptance criterion: savings >= 40 %.

2. Sibling run isolation
   When Run A crashes, concurrent Runs B and C must still reach
   "completed" without delay or data contamination.

How crashes are modelled
------------------------
S4 (persona voting) is the dominant LLM stage in production (100 calls).
The experiment crashes Run A after processing K personas, writes a
checkpoint to Redis, then resumes only the remaining work.

API-call accounting
-------------------
Each stage has a fixed LLM-call cost:
  S1  : num_videos calls (one per video analysis)
  S3  : 1 call (script generation is sequential)
  S4  : num_personas calls (one per persona vote)
  S6  : top_n calls (one per personalized script)
  S2, S5 : pure-Python aggregation / ranking — no LLM calls

A "crash at 50 % of S4" means:
  full_restart  = num_videos + 1 + num_personas + top_n = 15
  recovery      = (num_personas − checkpoint_s4) + top_n = 6
  saved         = 9 / 15 = 60 %  ✓

Run:
    pytest tests/experiments/test_failure_recovery.py -v -s
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
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

# ---------------------------------------------------------------------------
# Experiment parameters
# ---------------------------------------------------------------------------

NUM_VIDEOS: int = 4      # S1 API calls per run
NUM_PERSONAS: int = 8    # S4 API calls per run
TOP_N: int = 2           # S6 API calls per run
# Total per full run: 4 + 1 + 8 + 2 = 15

# Crash points: how many S4 (persona) tasks complete before crash
CRASH_SCENARIOS: list[tuple[str, int]] = [
    ("25%_into_S4", 2),   # 2/8 done → saves (4+1+2)/15 = 46.7 %
    ("50%_into_S4", 4),   # 4/8 done → saves (4+1+4)/15 = 60.0 %
    ("75%_into_S4", 6),   # 6/8 done → saves (4+1+6)/15 = 73.3 %
]

MIN_SAVINGS_PCT: float = 0.40   # acceptance criterion


# ---------------------------------------------------------------------------
# Helpers: call-count arithmetic
# ---------------------------------------------------------------------------


def _full_restart_calls(config: PipelineConfig) -> int:
    """Total LLM calls needed for a cold restart (no checkpoint)."""
    return config.num_videos + 1 + config.num_personas + config.top_n


def _recovery_calls(config: PipelineConfig, checkpoint_s4: int) -> int:
    """LLM calls needed when resuming after S1+S3 are done and S4 is at checkpoint.

    S1 result keys are already in Redis — no re-analysis needed.
    S3 was sequential and stored — no regeneration needed.
    S4 resumes from checkpoint_s4 (skips already-voted personas).
    S6 always runs in full (top-N scripts still need personalization).
    """
    remaining_s4 = max(0, config.num_personas - checkpoint_s4)
    return remaining_s4 + config.top_n


def _savings_pct(full: int, recovery: int) -> float:
    return (full - recovery) / full if full > 0 else 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def shared_redis() -> RedisClient:
    fake = fake_aioredis.FakeRedis(decode_responses=True)
    client = RedisClient.__new__(RedisClient)
    client._redis = fake
    yield client
    await fake.aclose()


@pytest_asyncio.fixture
async def isolated_redis() -> RedisClient:
    """Fresh Redis instance — used by tests that need a clean slate."""
    fake = fake_aioredis.FakeRedis(decode_responses=True)
    client = RedisClient.__new__(RedisClient)
    client._redis = fake
    yield client
    await fake.aclose()


# ---------------------------------------------------------------------------
# Pipeline driver helpers
# ---------------------------------------------------------------------------


def _config(run_id: str) -> PipelineConfig:
    return PipelineConfig(
        run_id=run_id,
        session_id=f"sess-{run_id}",
        reasoning_model="kimi",
        creator_profile=CreatorProfile(
            tone="casual", vocabulary=[], catchphrases=[], topics_to_avoid=[]
        ),
        num_videos=NUM_VIDEOS,
        num_scripts=3,
        num_personas=NUM_PERSONAS,
        top_n=TOP_N,
    )


def _videos(run_id: str) -> list[VideoInput]:
    return [
        VideoInput(
            video_id=f"{run_id}:v{i}",
            transcript=None,
            description=None,
            duration=30.0,
            engagement={},
        )
        for i in range(NUM_VIDEOS)
    ]



async def _seed_s6_output(redis: RedisClient, run_id: str, config: PipelineConfig) -> None:
    """Write the S5 rankings and S6 results that s5/s6 tasks would produce."""
    script_id = f"s:{run_id}"
    rankings = S5Rankings(
        top_10=[RankedScript(script_id=script_id, vote_count=2, score=10.0, rank=1)],
        total_votes_cast=config.num_personas,
    )
    await redis.set(f"top_scripts:{run_id}", rankings.model_dump_json())

    for i in range(config.top_n):
        sid = f"s:{run_id}:{i}" if i > 0 else script_id
        candidate = CandidateScript(
            script_id=sid,
            pattern_used="p",
            hook="h",
            body="b",
            payoff="pay",
            estimated_duration=30.0,
            structural_notes="",
        )
        result = FinalResult(
            script_id=sid,
            original_script=candidate,
            personalized_script="personalized",
            video_prompt="prompt",
            rank=i + 1,
            vote_score=10.0,
        )
        await redis.set(f"result:s6:{run_id}:{sid}", result.model_dump_json())


async def _drive_to_completion(redis: RedisClient, run_id: str) -> None:
    """Full no-crash run through all 6 stages."""
    config = _config(run_id)
    videos = _videos(run_id)
    orch = Orchestrator(redis)

    await orch.start(run_id, config, videos)
    for video in videos:
        await orch.on_s1_complete(run_id, video.video_id)
    await orch.on_s2_complete(run_id, pattern_count=4)
    await orch.on_s3_complete(run_id)
    for i in range(config.num_personas):
        await orch.on_s4_complete(run_id, f"persona_{i}", top_5=[f"s:{run_id}"])
    await _seed_s6_output(redis, run_id, config)
    await orch.on_s5_complete(run_id)
    for i in range(config.top_n):
        sid = f"s:{run_id}:{i}" if i > 0 else f"s:{run_id}"
        await orch.on_s6_complete(run_id, sid)


async def _drive_and_crash_at_s4(
    redis: RedisClient, run_id: str, s4_crash_at: int
) -> None:
    """Drive run through S1→S2→S3, then partial S4, then crash.

    Writes checkpoints so recovery can resume without redoing completed work.
    """
    config = _config(run_id)
    videos = _videos(run_id)
    orch = Orchestrator(redis)

    # S1 — all videos analyzed
    await orch.start(run_id, config, videos)
    for video in videos:
        await orch.on_s1_complete(run_id, video.video_id)

    # S2 → S3 — both sequential, both complete before S4
    await orch.on_s2_complete(run_id, pattern_count=4)
    await orch.on_s3_complete(run_id)

    # S4 partial — s4_crash_at personas vote, then worker is "killed"
    # on_s4_complete writes checkpoint:{run_id}:s4 automatically after each call
    for i in range(s4_crash_at):
        await orch.on_s4_complete(run_id, f"persona_{i}", top_5=[f"s:{run_id}"])


async def _resume_from_checkpoint(redis: RedisClient, run_id: str) -> None:
    """Resume a crashed run using stored checkpoint data.

    Reads checkpoint keys to determine remaining work and drives the
    run to completion from that point forward.
    """
    config = _config(run_id)
    orch = Orchestrator(redis)

    s4_done = await redis.read_checkpoint(run_id, "s4") or 0
    remaining_personas = range(s4_done, config.num_personas)

    # Resume S4 from checkpoint
    for i in remaining_personas:
        await orch.on_s4_complete(run_id, f"persona_{i}", top_5=[f"s:{run_id}"])

    # S5 and S6 run in full (not checkpointed)
    await _seed_s6_output(redis, run_id, config)
    await orch.on_s5_complete(run_id)
    for i in range(config.top_n):
        sid = f"s:{run_id}:{i}" if i > 0 else f"s:{run_id}"
        await orch.on_s6_complete(run_id, sid)


# ---------------------------------------------------------------------------
# Metrics dataclass
# ---------------------------------------------------------------------------


@dataclass
class RecoveryMetrics:
    label: str
    s4_crash_at: int
    full_restart_calls: int
    recovery_calls: int

    @property
    def savings_pct(self) -> float:
        return _savings_pct(self.full_restart_calls, self.recovery_calls)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_celery():
    patches = [
        patch("app.workers.tasks.s1_analyze_task"),
        patch("app.workers.tasks.s2_aggregate_task"),
        patch("app.workers.tasks.s3_generate_task"),
        patch("app.workers.tasks.s4_vote_task"),
        patch("app.workers.tasks.s5_rank_task"),
        patch("app.workers.tasks.s6_personalize_task"),
    ]
    mocks = [p.start() for p in patches]
    for m in mocks:
        m.delay = MagicMock()
    yield
    for p in patches:
        p.stop()


class TestFailureRecovery:
    """M5-2: Failure recovery + run isolation."""

    async def test_checkpoint_saves_40pct_calls_at_50pct_crash(
        self, isolated_redis: RedisClient
    ) -> None:
        """Crash at 50 % of S4 saves >= 40 % API calls vs full restart."""
        config = _config("run-crash-50pct")
        s4_crash_at = NUM_PERSONAS // 2  # 50 %

        full = _full_restart_calls(config)
        recovery = _recovery_calls(config, s4_crash_at)
        savings = _savings_pct(full, recovery)

        assert savings >= MIN_SAVINGS_PCT, (
            f"Expected >= {MIN_SAVINGS_PCT:.0%} savings at 50% crash, "
            f"got {savings:.1%}  (full={full}, recovery={recovery})"
        )

    async def test_all_crash_scenarios_save_over_40pct(
        self, isolated_redis: RedisClient
    ) -> None:
        """All three crash points (25 %, 50 %, 75 % into S4) save >= 40 %."""
        config = _config("run-scenarios")
        results: list[RecoveryMetrics] = []

        for label, s4_crash_at in CRASH_SCENARIOS:
            full = _full_restart_calls(config)
            recovery = _recovery_calls(config, s4_crash_at)
            results.append(RecoveryMetrics(label, s4_crash_at, full, recovery))

        _print_recovery_table(results)

        for m in results:
            assert m.savings_pct >= MIN_SAVINGS_PCT, (
                f"[{m.label}] Expected >= {MIN_SAVINGS_PCT:.0%} savings, "
                f"got {m.savings_pct:.1%}"
            )

    async def test_crashed_run_resumes_to_completed(
        self, isolated_redis: RedisClient
    ) -> None:
        """Run A crashes mid-S4, resumes from checkpoint, reaches 'completed'."""
        run_id = "run-resume-test"
        s4_crash_at = NUM_PERSONAS // 2

        await _drive_and_crash_at_s4(isolated_redis, run_id, s4_crash_at)

        # Verify checkpoint was written
        cp = await isolated_redis.read_checkpoint(run_id, "s4")
        assert cp == s4_crash_at, f"Expected checkpoint s4={s4_crash_at}, got {cp}"

        # Resume from checkpoint
        await _resume_from_checkpoint(isolated_redis, run_id)

        status = await isolated_redis.get(f"run:{run_id}:status")
        assert status == "completed", f"Expected 'completed' after recovery, got {status!r}"

    async def test_sibling_runs_unaffected_by_crash(
        self, shared_redis: RedisClient
    ) -> None:
        """Runs B and C reach 'completed' even while Run A crashes."""
        run_a, run_b, run_c = "run-crash-a", "run-ok-b", "run-ok-c"
        s4_crash_at = NUM_PERSONAS // 2

        async def crash_a() -> None:
            await _drive_and_crash_at_s4(shared_redis, run_a, s4_crash_at)

        await asyncio.gather(
            crash_a(),
            _drive_to_completion(shared_redis, run_b),
            _drive_to_completion(shared_redis, run_c),
        )

        # Run A should still be mid-flight (crashed, not completed)
        status_a = await shared_redis.get(f"run:{run_a}:status")
        assert status_a == "running", (
            f"Run A should be 'running' (crashed, not resumed) — got {status_a!r}"
        )

        # Runs B and C must have completed successfully
        for run_id in (run_b, run_c):
            status = await shared_redis.get(f"run:{run_id}:status")
            assert status == "completed", (
                f"Sibling {run_id} should be 'completed' but got {status!r}"
            )

    async def test_crash_leaves_no_contamination_in_siblings(
        self, shared_redis: RedisClient
    ) -> None:
        """Run A's partial S4 state does not appear in B or C's results."""
        run_a, run_b, run_c = "run-contam-a", "run-contam-b", "run-contam-c"

        await asyncio.gather(
            _drive_and_crash_at_s4(shared_redis, run_a, NUM_PERSONAS // 2),
            _drive_to_completion(shared_redis, run_b),
            _drive_to_completion(shared_redis, run_c),
        )

        for run_id in (run_b, run_c):
            # S4 done counter must equal NUM_PERSONAS (not contaminated by A's partial count)
            s4_done = await shared_redis.get(f"run:{run_id}:s4:done")
            assert s4_done == str(NUM_PERSONAS), (
                f"{run_id}: s4:done={s4_done!r}, expected {NUM_PERSONAS!r}"
            )

            # Final results must only reference this run's scripts
            raw = await shared_redis.get(f"results:final:{run_id}")
            assert raw is not None, f"{run_id}: no final results"
            output = json.loads(raw)
            for r in output["results"]:
                assert run_id in r["script_id"], (
                    f"{run_id}: result contains foreign script_id={r['script_id']!r}"
                )


# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------


def _print_recovery_table(rows: list[RecoveryMetrics]) -> None:
    config = _config("dummy")
    total = _full_restart_calls(config)

    print()
    print("=" * 60)
    print("M5-2: Failure Recovery — API Call Savings")
    print(f"  Full run = {total} calls  "
          f"(S1={config.num_videos} + S3=1 + S4={config.num_personas} + S6={config.top_n})")
    print("=" * 60)
    print(f"{'Scenario':<20}  {'full':>6}  {'recovery':>9}  {'saved':>8}  {'pass':>5}")
    print("-" * 60)
    for m in rows:
        mark = "✓" if m.savings_pct >= MIN_SAVINGS_PCT else "✗"
        print(
            f"{m.label:<20}  {m.full_restart_calls:>6}  "
            f"{m.recovery_calls:>9}  {m.savings_pct:>8.1%}  {mark:>5}"
        )
    print("=" * 60)
    print()


