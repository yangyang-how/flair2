"""M5-3: Cross-user cache concurrency experiment.

Simulates K concurrent pipeline runs on the same dataset, comparing:

  (a) naive GET/SET  — each run independently checks then fills the cache.
      When K runs start simultaneously, all see None and all compute the same
      video → duplicate LLM calls proportional to K.

  (b) SETNX via cache_get_or_compute — first run wins the sentinel, computes
      once; all other runs poll and reuse the result.
      Total LLM calls == NUM_VIDEOS regardless of K.

Measures total LLM calls and duplicates saved.
Closes #43.
"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

import fakeredis.aioredis

from app.infra.redis_client import CACHE_SENTINEL, RedisClient

# ── Experiment parameters ────────────────────────────────────────────────────
NUM_VIDEOS: int = 20            # simulated S1 dataset size (one LLM call per video)
LLM_LATENCY_S: float = 0.010   # simulated LLM call duration (10 ms)
K_VALUES: list[int] = [2, 5, 10]

# ── Fast-polling constants for experiment speed ──────────────────────────────
# Production code uses CACHE_POLL_INTERVAL=0.5 s / CACHE_POLL_TIMEOUT=30 s,
# which is too slow for a 10 ms simulated latency.  The subclass below uses
# 20 ms poll / 5 s timeout so the full suite finishes in < 5 s.
_FAST_POLL_INTERVAL_S: float = 0.020
_FAST_POLL_TIMEOUT_S: float = 5.0


# ── Subclass overriding poll intervals only ──────────────────────────────────

class _FastCacheClient(RedisClient):
    """RedisClient with faster loser-side polling for experiment speed.

    The SETNX logic is byte-for-byte identical to the production implementation
    in cache_get_or_compute; only the two timing constants differ.
    """

    async def cache_get_or_compute(
        self,
        cache_key: str,
        compute_fn: Callable[[], Awaitable[str]],
        ttl: int = 3600,
    ) -> str:
        cached = await self.get(cache_key)
        if cached is not None and cached != CACHE_SENTINEL:
            return cached

        if cached is None:
            won = await self.setnx(cache_key, CACHE_SENTINEL, ttl=60)
            if won:
                try:
                    result = await compute_fn()
                    await self.set(cache_key, result, ttl=ttl)
                    return result
                except Exception:
                    await self.delete(cache_key)
                    raise

        # Loser path — fast polling for experiment
        elapsed = 0.0
        while elapsed < _FAST_POLL_TIMEOUT_S:
            await asyncio.sleep(_FAST_POLL_INTERVAL_S)
            elapsed += _FAST_POLL_INTERVAL_S
            val = await self.get(cache_key)
            if val is not None and val != CACHE_SENTINEL:
                return val

        return await self.cache_get_or_compute(cache_key, compute_fn, ttl)


# ── Metrics ──────────────────────────────────────────────────────────────────

@dataclass
class CacheTrial:
    k: int
    mode: str        # "naive" | "setnx"
    total_calls: int

    @property
    def duplicate_calls(self) -> int:
        """LLM calls above the minimum (NUM_VIDEOS)."""
        return max(0, self.total_calls - NUM_VIDEOS)

    @property
    def savings_pct(self) -> float:
        """% of calls eliminated by SETNX vs naive at the same K."""
        return (self.duplicate_calls / self.total_calls * 100) if self.total_calls > 0 else 0.0


# ── Call counter ─────────────────────────────────────────────────────────────

class _CallCounter:
    """Counts compute invocations and simulates LLM latency."""

    def __init__(self) -> None:
        self.count: int = 0

    async def compute(self) -> str:
        await asyncio.sleep(LLM_LATENCY_S)
        self.count += 1
        return "llm_result"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client() -> _FastCacheClient:
    """Return a fresh in-memory Redis client backed by fakeredis."""
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    client = _FastCacheClient.__new__(_FastCacheClient)
    client._redis = fake
    return client


async def _run_naive(k: int) -> CacheTrial:
    """K concurrent runs using naive GET → compute → SET (no SETNX)."""
    redis = _make_client()
    counter = _CallCounter()

    async def one_run() -> None:
        for video_id in range(NUM_VIDEOS):
            key = f"cache:s1:video:{video_id}"
            cached = await redis.get(key)
            if cached is None:
                result = await counter.compute()
                await redis.set(key, result)

    await asyncio.gather(*[one_run() for _ in range(k)])
    return CacheTrial(k=k, mode="naive", total_calls=counter.count)


async def _run_setnx(k: int) -> CacheTrial:
    """K concurrent runs sharing cache via SETNX cache_get_or_compute."""
    redis = _make_client()
    counter = _CallCounter()

    async def one_run() -> None:
        for video_id in range(NUM_VIDEOS):
            key = f"cache:s1:video:{video_id}"
            await redis.cache_get_or_compute(key, counter.compute)

    await asyncio.gather(*[one_run() for _ in range(k)])
    return CacheTrial(k=k, mode="setnx", total_calls=counter.count)


# ── Output ────────────────────────────────────────────────────────────────────

def _print_table(pairs: list[tuple[CacheTrial, CacheTrial]]) -> None:
    sep = "=" * 70
    print(f"\n{sep}")
    print("M5-3: Cross-user Cache Concurrency Results")
    print(f"  NUM_VIDEOS={NUM_VIDEOS}, LLM_LATENCY={int(LLM_LATENCY_S * 1000)}ms")
    print(sep)
    print(f"{'K':>6}  {'naive calls':>12}  {'setnx calls':>12}  {'saved':>8}  {'savings%':>9}")
    print("-" * 70)
    for naive, setnx in pairs:
        saved = naive.total_calls - setnx.total_calls
        pct = saved / naive.total_calls * 100 if naive.total_calls > 0 else 0.0
        print(
            f"{naive.k:>6}  {naive.total_calls:>12}  {setnx.total_calls:>12}"
            f"  {saved:>8}  {pct:>8.1f}%"
        )
    print(sep)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestCacheConcurrency:
    async def test_setnx_exactly_num_videos_calls(self) -> None:
        """SETNX makes exactly NUM_VIDEOS LLM calls regardless of K.

        Core acceptance criterion from issue #43: one LLM call per unique
        video across all concurrent runs — no matter how many tenants race.
        """
        trial = await _run_setnx(k=10)
        assert trial.total_calls == NUM_VIDEOS, (
            f"Expected exactly {NUM_VIDEOS} LLM calls with SETNX at K=10, "
            f"got {trial.total_calls}"
        )

    async def test_naive_duplicates_grow_with_k(self) -> None:
        """Naive GET/SET produces duplicate calls that grow with K.

        Without the SETNX sentinel, concurrent runs that check the cache
        simultaneously all see None and all compute — wasting API quota.
        """
        results: list[CacheTrial] = []
        for k in K_VALUES:
            results.append(await _run_naive(k=k))

        # Total calls must grow monotonically with K
        for i in range(1, len(results)):
            assert results[i].total_calls >= results[i - 1].total_calls, (
                f"Expected more calls at K={results[i].k} than K={results[i - 1].k}, "
                f"got {results[i].total_calls} vs {results[i - 1].total_calls}"
            )

        k10 = next(r for r in results if r.k == 10)
        assert k10.duplicate_calls > 0, (
            f"Expected duplicate calls with naive at K=10, got {k10.total_calls} total "
            f"({k10.duplicate_calls} duplicates)"
        )

    async def test_setnx_always_num_videos_across_all_k(self) -> None:
        """SETNX holds exactly NUM_VIDEOS calls at every K value."""
        for k in K_VALUES:
            trial = await _run_setnx(k=k)
            assert trial.total_calls == NUM_VIDEOS, (
                f"Expected {NUM_VIDEOS} calls with SETNX at K={k}, got {trial.total_calls}"
            )

    async def test_results_table_all_k(self) -> None:
        """Print full results table and verify acceptance criteria from #43."""
        pairs: list[tuple[CacheTrial, CacheTrial]] = []
        for k in K_VALUES:
            naive = await _run_naive(k=k)
            setnx = await _run_setnx(k=k)
            pairs.append((naive, setnx))

        _print_table(pairs)

        all_setnx_exact = all(setnx.total_calls == NUM_VIDEOS for _, setnx in pairs)
        all_naive_dup = all(naive.duplicate_calls > 0 for naive, _ in pairs)

        print("\nAcceptance criteria (issue #43):")
        print(
            f"  [{'✓' if all_setnx_exact else '✗'}] setnx calls == {NUM_VIDEOS} for all K  →  "
            f"{[s.total_calls for _, s in pairs]}"
        )
        print(
            f"  [{'✓' if all_naive_dup else '✗'}] naive has duplicates for all K  →  "
            f"{[n.duplicate_calls for n, _ in pairs]} dupes"
        )

        assert all_setnx_exact
        assert all_naive_dup


# ── Scale extension ───────────────────────────────────────────────────────────
# K=50/100: actual simulation (asyncio, runs in < 5s)
# K=1k+:    analytical projection — formulas are exact by construction:
#             naive_calls(K) = K * NUM_VIDEOS          (every run races every video)
#             setnx_calls(K) = NUM_VIDEOS              (SETNX guarantee, always)
#             savings_pct(K) = (K-1) / K * 100

K_SCALE_SIMULATED: list[int] = [50, 100]
K_SCALE_PROJECTED: list[int] = [1_000, 10_000, 50_000, 100_000]


def _project_naive_calls(k: int) -> int:
    return k * NUM_VIDEOS


def _project_savings_pct(k: int) -> float:
    return (k - 1) / k * 100


def _print_scale_table(
    simulated: list[tuple[CacheTrial, CacheTrial]],
    projected_ks: list[int],
) -> None:
    sep = "=" * 68
    print(f"\n{sep}")
    print("M5-3 Scale Projection — Cache Concurrency at Large K")
    print(f"  NUM_VIDEOS={NUM_VIDEOS}, PROVIDER_LIMIT=1 per video (SETNX)")
    print(sep)
    print(f"{'K':>8}  {'type':>10}  {'naive calls':>12}  {'setnx calls':>12}  {'savings%':>9}")
    print("-" * 68)
    for naive, setnx in simulated:
        pct = (naive.total_calls - setnx.total_calls) / naive.total_calls * 100
        print(
            f"{naive.k:>8}  {'simulated':>10}  {naive.total_calls:>12}  "
            f"{setnx.total_calls:>12}  {pct:>8.1f}%"
        )
    for k in projected_ks:
        naive_c = _project_naive_calls(k)
        setnx_c = NUM_VIDEOS
        pct = _project_savings_pct(k)
        print(f"{k:>8,}  {'projected':>10}  {naive_c:>12,}  {setnx_c:>12}  {pct:>8.3f}%")
    print(sep)
    print()
    print("  naive calls  = K × NUM_VIDEOS  (all runs race every video)")
    print("  setnx calls  = NUM_VIDEOS      (SETNX guarantee, always fixed)")
    print("  savings%     = (K-1) / K × 100")


class TestCacheConcurrencyScale:
    async def test_scale_simulated_k50_k100(self) -> None:
        """Actual simulation for K=50 and K=100.

        Verifies the SETNX guarantee holds at higher concurrency.
        """
        for k in K_SCALE_SIMULATED:
            setnx = await _run_setnx(k=k)
            assert setnx.total_calls == NUM_VIDEOS, (
                f"SETNX must use exactly {NUM_VIDEOS} calls at K={k}, got {setnx.total_calls}"
            )
            naive = await _run_naive(k=k)
            assert naive.total_calls == k * NUM_VIDEOS, (
                f"Naive must use K×NUM_VIDEOS={k * NUM_VIDEOS} calls at K={k}, "
                f"got {naive.total_calls}"
            )

    async def test_scale_projection_table(self) -> None:
        """Print unified table: simulated K=50/100 + projected K=1k–100k."""
        simulated_pairs: list[tuple[CacheTrial, CacheTrial]] = []
        for k in K_SCALE_SIMULATED:
            naive = await _run_naive(k=k)
            setnx = await _run_setnx(k=k)
            simulated_pairs.append((naive, setnx))

        _print_scale_table(simulated_pairs, K_SCALE_PROJECTED)
