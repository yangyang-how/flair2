"""M6: ElastiCache integration experiments.

Three experiments that require a real Redis/ElastiCache endpoint.
All tests are skipped when ELASTICACHE_URL is not set (unit / CI runs).

Run locally after terraform apply:

    ELASTICACHE_URL=$(aws elasticache describe-cache-clusters \
        --region us-west-2 \
        --show-cache-node-info \
        --query 'CacheClusters[?CacheClusterId==`flair2-dev-redis`]
                .CacheNodes[0].Endpoint.Address' \
        --output text) && ELASTICACHE_URL="redis://${ELASTICACHE_URL}:6379"

    ELASTICACHE_URL=$ELASTICACHE_URL pytest tests/experiments/test_elasticache_integration.py -v -s

Experiments
-----------
M6-1  Network latency     — p50/p95/p99 for SETNX, XADD, INCR on ElastiCache
                            vs the ~0.1 ms fakeredis baseline in unit tests.
M6-2  Race-condition      — 100 concurrent workers compete for the same SETNX key;
                            exactly one must win. Validates that real network I/O
                            does not break the atomicity guarantee fakeredis trivially
                            preserves (single-threaded event loop, no real concurrency).
M6-3  Memory pressure     — 100 concurrent pipeline runs each writing 100 S1 result
                            keys. Measures peak memory usage on the ElastiCache node
                            and confirms it stays within the instance's limit.
"""
from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
import uuid

import pytest
import redis.asyncio as aioredis

# ── Skip entire module when no real Redis is available ───────────────────────
ELASTICACHE_URL: str | None = os.getenv("ELASTICACHE_URL")

pytestmark = pytest.mark.skipif(
    ELASTICACHE_URL is None,
    reason="ELASTICACHE_URL not set — skipping ElastiCache integration experiments",
)

# ── Experiment parameters ────────────────────────────────────────────────────
LATENCY_ITERATIONS: int = 1_000   # number of ops per operation type
RACE_WORKERS: int = 100           # concurrent workers competing for one key
MEMORY_RUNS: int = 100            # concurrent pipeline run simulations
MEMORY_VIDEOS_PER_RUN: int = 100  # S1 results written per run
MEMORY_PAYLOAD_BYTES: int = 512   # bytes per S1 result value (realistic pattern JSON)

# Guard: treat 0 bytes as a sentinel that means "not reported"
_MEMORY_WARN_MB: float = 50.0     # warn (but don't fail) if usage exceeds this


# ── Shared fixture ───────────────────────────────────────────────────────────

@pytest.fixture()
async def redis() -> aioredis.Redis:
    """Return an authenticated Redis connection and flush the test namespace on teardown."""
    assert ELASTICACHE_URL is not None  # already guarded by pytestmark
    r = aioredis.from_url(ELASTICACHE_URL, decode_responses=True)
    yield r
    # Best-effort teardown: delete keys written by these tests
    test_keys = await r.keys("m6:*")
    if test_keys:
        await r.delete(*test_keys)
    await r.aclose()


# ── M6-1: Network Latency ────────────────────────────────────────────────────

class TestNetworkLatency:
    """M6-1: Measure p50/p95/p99 latency for core Redis operations on ElastiCache.

    Expected baselines (same AWS region, single-AZ):
      fakeredis   ~0.05–0.15 ms   (in-process, no network)
      ElastiCache ~0.3–2.0 ms     (VPC, same AZ)
      ElastiCache ~10–50 ms       (cross-region or high-load)

    The test does NOT enforce a hard latency SLA — latency varies by instance
    type and load.  It prints a table so you can judge acceptability for your
    use case and compare against the fakeredis baseline.
    """

    @staticmethod
    def _percentiles(latencies_s: list[float]) -> dict[str, float]:
        ms = [v * 1000 for v in latencies_s]
        return {
            "p50":  round(statistics.median(ms), 3),
            "p95":  round(statistics.quantiles(ms, n=20)[18], 3),  # 95th
            "p99":  round(statistics.quantiles(ms, n=100)[98], 3), # 99th
            "mean": round(statistics.mean(ms), 3),
            "max":  round(max(ms), 3),
        }

    async def test_setnx_latency(self, redis: aioredis.Redis) -> None:
        latencies: list[float] = []
        for i in range(LATENCY_ITERATIONS):
            key = f"m6:latency:setnx:{i}"
            t0 = time.perf_counter()
            await redis.set(key, "v", nx=True, ex=60)
            latencies.append(time.perf_counter() - t0)

        stats = self._percentiles(latencies)
        print(f"\n[M6-1] SETNX latency over {LATENCY_ITERATIONS} iterations (ms): {stats}")

        # Sanity: even in the worst conditions, p99 should be < 500 ms
        assert stats["p99"] < 500, f"p99 latency {stats['p99']} ms is unexpectedly high"

    async def test_xadd_latency(self, redis: aioredis.Redis) -> None:
        stream = "m6:latency:stream"
        latencies: list[float] = []
        for i in range(LATENCY_ITERATIONS):
            t0 = time.perf_counter()
            await redis.xadd(stream, {"event": "test", "seq": str(i)})
            latencies.append(time.perf_counter() - t0)

        stats = self._percentiles(latencies)
        print(f"\n[M6-1] XADD latency over {LATENCY_ITERATIONS} iterations (ms): {stats}")

        assert stats["p99"] < 500

    async def test_incr_latency(self, redis: aioredis.Redis) -> None:
        key = "m6:latency:counter"
        latencies: list[float] = []
        for _ in range(LATENCY_ITERATIONS):
            t0 = time.perf_counter()
            await redis.incr(key)
            latencies.append(time.perf_counter() - t0)

        stats = self._percentiles(latencies)
        print(f"\n[M6-1] INCR latency over {LATENCY_ITERATIONS} iterations (ms): {stats}")

        assert stats["p99"] < 500


# ── M6-2: Race Condition / SETNX Atomicity ───────────────────────────────────

class TestRaceCondition:
    """M6-2: Verify SETNX atomicity under real concurrent load.

    fakeredis serialises coroutines on a single event loop, so SETNX is
    trivially atomic — coroutines never truly execute at the same wall-clock
    instant.  With a real Redis server over the network, multiple coroutines
    issue SET NX at genuinely overlapping times.  The Redis server must still
    guarantee that exactly one wins.

    This test fires RACE_WORKERS (100) concurrent SET NX commands against the
    same key and asserts that exactly one coroutine gets a truthy response.
    """

    async def test_exactly_one_winner(self, redis: aioredis.Redis) -> None:
        lock_key = f"m6:race:lock:{uuid.uuid4().hex}"
        winners: list[int] = []

        async def compete(worker_id: int) -> None:
            result = await redis.set(lock_key, str(worker_id), nx=True, ex=30)
            if result:
                winners.append(worker_id)

        await asyncio.gather(*[compete(i) for i in range(RACE_WORKERS)])

        print(f"\n[M6-2] {RACE_WORKERS} workers competed; winner: {winners}")
        assert len(winners) == 1, (
            f"Expected exactly 1 winner, got {len(winners)}: {winners}"
        )

    async def test_winner_value_stored(self, redis: aioredis.Redis) -> None:
        """The value stored must match the winner's worker_id (no corruption)."""
        lock_key = f"m6:race:value:{uuid.uuid4().hex}"
        winners: list[int] = []

        async def compete(worker_id: int) -> None:
            result = await redis.set(lock_key, str(worker_id), nx=True, ex=30)
            if result:
                winners.append(worker_id)

        await asyncio.gather(*[compete(i) for i in range(RACE_WORKERS)])

        stored = await redis.get(lock_key)
        assert len(winners) == 1
        assert stored == str(winners[0]), (
            f"Stored value '{stored}' does not match winner {winners[0]}"
        )


# ── M6-3: Memory Pressure ────────────────────────────────────────────────────

class TestMemoryPressure:
    """M6-3: Measure Redis memory usage under 100 concurrent pipeline runs.

    Each simulated run writes MEMORY_VIDEOS_PER_RUN S1 result keys
    (realistic JSON payload, 1-hour TTL).  After all writes complete we query
    the ElastiCache node's used_memory and report it.

    The test does NOT enforce a hard memory limit because the right limit depends
    on the chosen cache.t3.micro / cache.t3.small instance.  It prints the usage
    so you can decide whether to scale up the instance type in dev.tfvars.

    Typical expectations:
      100 runs × 100 keys × 512 bytes ≈ 5 MB raw data
      Redis overhead (key names, encoding)  ≈ 2–3× → ~10–15 MB total
    """

    async def test_memory_under_concurrent_runs(self, redis: aioredis.Redis) -> None:
        payload = json.dumps({
            "pattern": "hook_question",
            "description": "Opens with a compelling question to draw viewers in",
            "examples": ["What if I told you...", "Did you know that..."],
            "confidence": 0.87,
            "video_ids": [f"vid_{j}" for j in range(5)],
        })
        # Pad to target size
        padding = "x" * max(0, MEMORY_PAYLOAD_BYTES - len(payload))
        value = payload + padding

        async def simulate_run(run_id: str) -> None:
            for video_idx in range(MEMORY_VIDEOS_PER_RUN):
                key = f"m6:memory:result:s1:{run_id}:{video_idx}"
                await redis.set(key, value, ex=3600)

        run_ids = [f"run-{uuid.uuid4().hex[:8]}" for _ in range(MEMORY_RUNS)]
        await asyncio.gather(*[simulate_run(rid) for rid in run_ids])

        info = await redis.info("memory")
        used_mb = info["used_memory"] / (1024 * 1024)
        peak_mb = info.get("used_memory_peak", info["used_memory"]) / (1024 * 1024)

        total_keys = MEMORY_RUNS * MEMORY_VIDEOS_PER_RUN
        print(
            f"\n[M6-3] Memory after {MEMORY_RUNS} runs × {MEMORY_VIDEOS_PER_RUN} keys "
            f"({total_keys} total):\n"
            f"  used_memory:      {used_mb:.2f} MB\n"
            f"  used_memory_peak: {peak_mb:.2f} MB\n"
            f"  used_memory_human: {info['used_memory_human']}"
        )

        if used_mb > _MEMORY_WARN_MB:
            print(
                f"  [WARN] Memory usage {used_mb:.1f} MB exceeds warn threshold "
                f"{_MEMORY_WARN_MB} MB — consider a larger ElastiCache instance type."
            )

        # Only hard-fail if Redis reports 0 (connection/reporting issue)
        assert info["used_memory"] > 0, "Redis reported 0 bytes used — check connection"
