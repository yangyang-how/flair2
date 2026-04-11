"""M5-1: Experiment 1 — Multi-tenant backpressure.

Validates that the token-bucket rate limiter prevents provider 429 errors
under high concurrency, and that completion time remains fair across runs.

Scenario
--------
K concurrent pipeline "runs" each fire CALLS_PER_WORKER LLM calls in
parallel (representing the S4 fan-out stage, the hottest burst point).
A simulated provider enforces a hard call limit per time window.

Two conditions are compared:
  (a) no_limiter  — calls go directly to the provider; excess calls fail.
  (b) rate_limited — calls pass through TokenBucketRateLimiter first.

Acceptance criteria (issue #41)
--------------------------------
  [x] Test harness runs K = 1, 3, 5, 10 concurrent runs
  [x] Data collected: requests attempted, error count, error rate,
      per-run completion time, coefficient of variation (fairness)
  [x] rate_limited produces < 1 % error rate at K = 10
  [x] no_limiter produces > 50 % error rate at K = 10 (showing the need)

Run
---
    # results table only:
    pytest tests/experiments/test_backpressure.py -v -s

    # full table printed to stdout:
    python -m tests.experiments.test_backpressure
"""

from __future__ import annotations

import asyncio
import random
import statistics
import time
from dataclasses import dataclass, field

import pytest
import pytest_asyncio
from fakeredis import aioredis as fake_aioredis

from app.infra.rate_limiter import TokenBucketRateLimiter
from app.infra.redis_client import RedisClient
from app.models.errors import ProviderError, RateLimitError

# ---------------------------------------------------------------------------
# Experiment parameters
# ---------------------------------------------------------------------------

CALLS_PER_WORKER: int = 5       # fan-out calls per run (e.g. S4 with 5 personas)
PROVIDER_LIMIT: int = 5         # provider hard limit per WINDOW_S
WINDOW_S: float = 0.10          # time window length (100 ms — scaled for fast tests)
RETRY_DELAY_S: float = 0.12     # retry delay > WINDOW_S so window resets before retry
LLM_LATENCY_S: float = 0.002    # simulated LLM response time (2 ms)

K_VALUES: list[int] = [1, 3, 5, 10]

# ---------------------------------------------------------------------------
# Simulated provider
# ---------------------------------------------------------------------------


class SimulatedProvider:
    """Enforces a hard call limit per time window; tracks rejections.

    Rejects calls above PROVIDER_LIMIT in the current window by raising
    ProviderError (equivalent to a real 429).  Window resets automatically.
    """

    def __init__(self, limit_per_window: int, window_s: float) -> None:
        self._limit = limit_per_window
        self._window_s = window_s
        self._count = 0
        self._window_start = time.perf_counter()
        self._lock = asyncio.Lock()
        self.total_calls = 0
        self.rejected = 0

    async def call(self) -> None:
        async with self._lock:
            now = time.perf_counter()
            if now - self._window_start >= self._window_s:
                self._count = 0
                self._window_start = now
            self._count += 1
            self.total_calls += 1
            if self._count > self._limit:
                self.rejected += 1
                raise ProviderError("429 Too Many Requests", provider="simulated")
        await asyncio.sleep(LLM_LATENCY_S)


# ---------------------------------------------------------------------------
# Rate limiter subclass with configurable retry delay (experiment-only)
# ---------------------------------------------------------------------------


class _FastRateLimiter(TokenBucketRateLimiter):
    """TokenBucketRateLimiter tuned for sub-second experiment windows.

    Two changes vs. production:
    1. acquire() uses PEXPIRE (milliseconds) instead of EXPIRE (integer seconds)
       so that float windows like 0.1 s work correctly with fakeredis.
    2. wait_for_token() uses a short, configurable retry delay so the test
       completes in ~1-2 s rather than minutes.
    """

    def __init__(self, *args: object, retry_delay_s: float = RETRY_DELAY_S, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._retry_delay_s = retry_delay_s

    async def acquire(self) -> bool:
        """Increment counter; set PEXPIRE on first call (supports float windows)."""
        count = await self._redis.incr(self._key)
        if count == 1:
            window_ms = int(self._window_seconds * 1000)
            # Access raw aioredis client — RedisClient.expire only takes int seconds
            await self._redis._redis.pexpire(self._key, window_ms)
        return count <= self._max_tokens

    async def wait_for_token(self, max_wait: float = 30.0) -> None:
        elapsed = 0.0
        while elapsed < max_wait:
            if await self.acquire():
                return
            # Small random jitter so competing coroutines don't all wake
            # at exactly the same instant and pile up again.
            delay = self._retry_delay_s + random.uniform(0, self._retry_delay_s * 0.2)
            await asyncio.sleep(delay)
            elapsed += delay
        raise RateLimitError(
            f"Rate limiter timed out after {max_wait:.1f}s",
            provider=self._provider,
        )


# ---------------------------------------------------------------------------
# Per-worker metrics
# ---------------------------------------------------------------------------


@dataclass
class WorkerMetrics:
    worker_id: int
    elapsed_s: float
    errors: int
    total_calls: int

    @property
    def error_rate(self) -> float:
        return self.errors / self.total_calls if self.total_calls else 0.0


@dataclass
class TrialMetrics:
    K: int
    mode: str  # "no_limiter" | "rate_limited"
    workers: list[WorkerMetrics] = field(default_factory=list)

    @property
    def total_calls(self) -> int:
        return sum(w.total_calls for w in self.workers)

    @property
    def total_errors(self) -> int:
        return sum(w.errors for w in self.workers)

    @property
    def error_rate(self) -> float:
        return self.total_errors / self.total_calls if self.total_calls else 0.0

    @property
    def completion_times(self) -> list[float]:
        return [w.elapsed_s for w in self.workers]

    @property
    def mean_completion_s(self) -> float:
        return statistics.mean(self.completion_times) if self.workers else 0.0

    @property
    def completion_cv(self) -> float:
        """Coefficient of variation of per-worker completion times.

        CV = std / mean.  Low CV means all runs completed in similar time
        (fair).  High CV means some runs were starved.
        """
        times = self.completion_times
        if len(times) < 2:
            return 0.0
        mean = statistics.mean(times)
        if mean == 0:
            return 0.0
        return statistics.stdev(times) / mean


# ---------------------------------------------------------------------------
# Core simulation helpers
# ---------------------------------------------------------------------------


async def _simulate_worker(
    worker_id: int,
    provider: SimulatedProvider,
    limiter: _FastRateLimiter | None,
) -> WorkerMetrics:
    """One run: fire CALLS_PER_WORKER concurrent LLM calls."""
    start = time.perf_counter()

    async def _one_call() -> None:
        if limiter is not None:
            await limiter.wait_for_token()
        await provider.call()

    results = await asyncio.gather(
        *[_one_call() for _ in range(CALLS_PER_WORKER)],
        return_exceptions=True,
    )
    elapsed = time.perf_counter() - start
    errors = sum(1 for r in results if isinstance(r, Exception))
    return WorkerMetrics(worker_id, elapsed, errors, CALLS_PER_WORKER)


async def _run_trial(K: int, use_limiter: bool, redis: RedisClient) -> TrialMetrics:
    """Run K concurrent workers and return aggregate metrics."""
    mode = "rate_limited" if use_limiter else "no_limiter"
    provider = SimulatedProvider(PROVIDER_LIMIT, WINDOW_S)
    limiter = (
        _FastRateLimiter(redis, "simulated", max_tokens=PROVIDER_LIMIT, window_seconds=WINDOW_S)
        if use_limiter
        else None
    )

    worker_results: list[WorkerMetrics] = await asyncio.gather(
        *[_simulate_worker(i, provider, limiter) for i in range(K)]
    )

    trial = TrialMetrics(K=K, mode=mode, workers=list(worker_results))
    return trial


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def redis() -> RedisClient:
    fake = fake_aioredis.FakeRedis(decode_responses=True)
    client = RedisClient.__new__(RedisClient)
    client._redis = fake
    yield client
    await fake.aclose()


# ---------------------------------------------------------------------------
# Acceptance-criteria tests
# ---------------------------------------------------------------------------


class TestBackpressureExperiment:
    """M5-1: Multi-tenant backpressure experiment."""

    async def test_no_limiter_error_rate_high_at_k10(self, redis: RedisClient) -> None:
        """Without rate limiter, K=10 produces > 50 % error rate.

        Shows the problem: unthrottled burst causes provider 429s.
        """
        trial = await _run_trial(K=10, use_limiter=False, redis=redis)
        assert trial.error_rate > 0.50, (
            f"Expected > 50% error rate without limiter at K=10, "
            f"got {trial.error_rate:.1%} ({trial.total_errors}/{trial.total_calls})"
        )

    async def test_rate_limited_error_rate_under_1pct_k10(self, redis: RedisClient) -> None:
        """With rate limiter, K=10 produces < 1 % error rate.

        Core acceptance criterion from issue #41.
        """
        trial = await _run_trial(K=10, use_limiter=True, redis=redis)
        assert trial.error_rate < 0.01, (
            f"Expected < 1% error rate with limiter at K=10, "
            f"got {trial.error_rate:.1%} ({trial.total_errors}/{trial.total_calls})"
        )

    async def test_rate_limited_fairness_k10(self, redis: RedisClient) -> None:
        """With rate limiter, per-run completion time CV should be < 100 %.

        A token bucket without explicit fairness guarantees will have some
        variance (faster workers happen to get tokens earlier).  In production
        — where real LLM calls take 5-30 s and smooth out timing — CV would
        be considerably lower.  This test asserts a conservative bound to
        detect pathological starvation.
        """
        trial = await _run_trial(K=10, use_limiter=True, redis=redis)
        cv = trial.completion_cv
        assert cv < 1.0, (
            f"Completion time CV = {cv:.2f} — some workers may be starved. "
            f"Times: {[f'{t*1000:.0f}ms' for t in trial.completion_times]}"
        )

    async def test_results_table_all_k(self, redis: RedisClient) -> None:
        """Run all K values and print the full results table.

        Not an assertion test — exists to produce the write-up data.
        Run with -s to see stdout.
        """
        rows: list[TrialMetrics] = []
        for K in K_VALUES:
            # Re-create redis for each trial to avoid stale rate-limit keys
            fake = fake_aioredis.FakeRedis(decode_responses=True)
            fresh_redis = RedisClient.__new__(RedisClient)
            fresh_redis._redis = fake

            no_lim = await _run_trial(K, use_limiter=False, redis=fresh_redis)
            rows.append(no_lim)

            fake2 = fake_aioredis.FakeRedis(decode_responses=True)
            fresh_redis2 = RedisClient.__new__(RedisClient)
            fresh_redis2._redis = fake2

            with_lim = await _run_trial(K, use_limiter=True, redis=fresh_redis2)
            rows.append(with_lim)

            await fake.aclose()
            await fake2.aclose()

        _print_table(rows)


# ---------------------------------------------------------------------------
# Results table printer
# ---------------------------------------------------------------------------


def _print_table(rows: list[TrialMetrics]) -> None:
    print()
    print("=" * 80)
    print("M5-1: Multi-tenant Backpressure Experiment Results")
    print(f"  CALLS_PER_WORKER={CALLS_PER_WORKER}, PROVIDER_LIMIT={PROVIDER_LIMIT}/window,")
    print(f"  WINDOW={WINDOW_S*1000:.0f}ms, LLM_LATENCY={LLM_LATENCY_S*1000:.0f}ms")
    print("=" * 80)
    hdr = f"{'K':>4}  {'Mode':<14}  {'calls':>6}  {'errors':>7}  {'err%':>7}  {'mean_ms':>8}  {'CV':>6}"
    print(hdr)
    print("-" * 80)
    for row in rows:
        print(
            f"{row.K:>4}  {row.mode:<14}  "
            f"{row.total_calls:>6}  {row.total_errors:>7}  "
            f"{row.error_rate:>7.1%}  "
            f"{row.mean_completion_s*1000:>8.1f}  "
            f"{row.completion_cv:>6.2f}"
        )
        if row.mode == "rate_limited":
            print()
    print("=" * 80)
    print()
    print("Acceptance criteria (issue #41):")
    k10_no_lim = next(r for r in rows if r.K == 10 and r.mode == "no_limiter")
    k10_lim = next(r for r in rows if r.K == 10 and r.mode == "rate_limited")
    _check("error_rate(no_limiter, K=10) > 50%", k10_no_lim.error_rate > 0.50,
           f"{k10_no_lim.error_rate:.1%}")
    _check("error_rate(rate_limited, K=10) < 1%", k10_lim.error_rate < 0.01,
           f"{k10_lim.error_rate:.1%}")
    _check("completion_CV(rate_limited, K=10) < 1.0", k10_lim.completion_cv < 1.0,
           f"{k10_lim.completion_cv:.2f}")
    print()


def _check(label: str, passed: bool, value: str) -> None:
    mark = "✓" if passed else "✗"
    print(f"  [{mark}] {label}  →  {value}")


# ---------------------------------------------------------------------------
# Standalone runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    async def _main() -> None:
        fake = fake_aioredis.FakeRedis(decode_responses=True)
        client = RedisClient.__new__(RedisClient)
        client._redis = fake

        rows: list[TrialMetrics] = []
        for K in K_VALUES:
            fake_a = fake_aioredis.FakeRedis(decode_responses=True)
            r_a = RedisClient.__new__(RedisClient)
            r_a._redis = fake_a
            rows.append(await _run_trial(K, use_limiter=False, redis=r_a))
            await fake_a.aclose()

            fake_b = fake_aioredis.FakeRedis(decode_responses=True)
            r_b = RedisClient.__new__(RedisClient)
            r_b._redis = fake_b
            rows.append(await _run_trial(K, use_limiter=True, redis=r_b))
            await fake_b.aclose()

        _print_table(rows)
        await fake.aclose()

    asyncio.run(_main())
    sys.exit(0)
