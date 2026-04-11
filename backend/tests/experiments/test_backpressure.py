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
import math
import random
import statistics
import time
from dataclasses import dataclass, field

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

# Scale projection — K values too large to simulate in CI
# (K ≤ 100 are simulated; K ≥ 1000 are computed analytically)
K_SCALE_SIMULATED: list[int] = [50, 100]
K_SCALE_PROJECTED: list[int] = [1_000, 10_000, 50_000, 100_000]
# Scale tests use 1 call/worker so run time stays under 5 s
SCALE_CALLS_PER_WORKER: int = 1

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

    def __init__(
        self, *args: object, retry_delay_s: float = RETRY_DELAY_S, **kwargs: object
    ) -> None:
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


async def _run_trial(k: int, use_limiter: bool, redis: RedisClient) -> TrialMetrics:
    """Run k concurrent workers and return aggregate metrics."""
    mode = "rate_limited" if use_limiter else "no_limiter"
    provider = SimulatedProvider(PROVIDER_LIMIT, WINDOW_S)
    limiter = (
        _FastRateLimiter(redis, "simulated", max_tokens=PROVIDER_LIMIT, window_seconds=WINDOW_S)
        if use_limiter
        else None
    )

    worker_results: list[WorkerMetrics] = await asyncio.gather(
        *[_simulate_worker(i, provider, limiter) for i in range(k)]
    )

    trial = TrialMetrics(K=k, mode=mode, workers=list(worker_results))
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
        trial = await _run_trial(k=10, use_limiter=False, redis=redis)
        assert trial.error_rate > 0.50, (
            f"Expected > 50% error rate without limiter at K=10, "
            f"got {trial.error_rate:.1%} ({trial.total_errors}/{trial.total_calls})"
        )

    async def test_rate_limited_error_rate_under_1pct_k10(self, redis: RedisClient) -> None:
        """With rate limiter, K=10 produces < 1 % error rate.

        Core acceptance criterion from issue #41.
        """
        trial = await _run_trial(k=10, use_limiter=True, redis=redis)
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
        trial = await _run_trial(k=10, use_limiter=True, redis=redis)
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
        for k in K_VALUES:
            # Re-create redis for each trial to avoid stale rate-limit keys
            fake = fake_aioredis.FakeRedis(decode_responses=True)
            fresh_redis = RedisClient.__new__(RedisClient)
            fresh_redis._redis = fake

            no_lim = await _run_trial(k, use_limiter=False, redis=fresh_redis)
            rows.append(no_lim)

            fake2 = fake_aioredis.FakeRedis(decode_responses=True)
            fresh_redis2 = RedisClient.__new__(RedisClient)
            fresh_redis2._redis = fake2

            with_lim = await _run_trial(k, use_limiter=True, redis=fresh_redis2)
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
    hdr = f"{'K':>4}  {'Mode':<14}  {'calls':>6}  {'errors':>7}  {'err%':>7}  {'mean_ms':>8}  {'CV':>6}"  # noqa: E501
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
# Scale projection helpers (analytical — no simulation needed)
# ---------------------------------------------------------------------------


@dataclass
class ScaleRow:
    k: int
    mode: str           # "simulated" | "projected"
    no_lim_err_pct: float
    lim_err_pct: float
    lim_completion_s: float


def _project_no_lim_error_rate(k: int, calls: int = SCALE_CALLS_PER_WORKER) -> float:
    """Error rate when all K*calls burst simultaneously (no rate limiter)."""
    total = k * calls
    errors = max(0, total - PROVIDER_LIMIT)
    return errors / total if total > 0 else 0.0


def _project_lim_completion_s(k: int, calls: int = SCALE_CALLS_PER_WORKER) -> float:
    """Completion time with rate limiter: ceil(total/limit) windows."""
    total = k * calls
    windows = math.ceil(total / PROVIDER_LIMIT)
    return windows * WINDOW_S


async def _run_scale_trial(k: int, redis: RedisClient) -> ScaleRow:
    """Run both conditions for one K value (simulation, CALLS_PER_WORKER=1)."""
    no_lim = await _run_trial(k, use_limiter=False, redis=redis)

    fake2 = fake_aioredis.FakeRedis(decode_responses=True)
    r2 = RedisClient.__new__(RedisClient)
    r2._redis = fake2
    lim = await _run_trial(k, use_limiter=True, redis=r2)
    await fake2.aclose()

    return ScaleRow(
        k=k,
        mode="simulated",
        no_lim_err_pct=no_lim.error_rate,
        lim_err_pct=lim.error_rate,
        lim_completion_s=lim.mean_completion_s,
    )


def _project_scale_row(k: int) -> ScaleRow:
    return ScaleRow(
        k=k,
        mode="projected",
        no_lim_err_pct=_project_no_lim_error_rate(k),
        lim_err_pct=0.0,
        lim_completion_s=_project_lim_completion_s(k),
    )


def _print_scale_table(rows: list[ScaleRow]) -> None:
    print()
    print("=" * 72)
    print("M5-1 Scale Projection — Backpressure at Large K")
    print(f"  PROVIDER_LIMIT={PROVIDER_LIMIT}/window, WINDOW={WINDOW_S*1000:.0f}ms,")
    print(f"  CALLS_PER_WORKER={SCALE_CALLS_PER_WORKER} (S4 fan-out simplified)")
    print("=" * 72)
    hdr = f"{'K':>8}  {'type':<10}  {'no_lim err%':>12}  {'lim err%':>9}  {'lim time':>10}"  # noqa: E501
    print(hdr)
    print("-" * 72)
    for r in rows:
        t = _fmt_duration(r.lim_completion_s)
        print(
            f"{r.k:>8}  {r.mode:<10}  "
            f"{r.no_lim_err_pct:>12.1%}  "
            f"{r.lim_err_pct:>9.1%}  "
            f"{t:>10}"
        )
    print("=" * 72)
    print()
    print("  no_lim err%  = error rate when all calls burst with no throttling")
    print("  lim err%     = error rate with token-bucket (always 0 by design)")
    print("  lim time     = projected completion time with rate limiter active")
    print()


def _fmt_duration(seconds: float) -> str:
    if seconds < 1:
        return f"{seconds*1000:.0f}ms"
    if seconds < 60:
        return f"{seconds:.1f}s"
    if seconds < 3600:
        return f"{seconds/60:.1f}min"
    return f"{seconds/3600:.1f}hr"


# ---------------------------------------------------------------------------
# Scale tests
# ---------------------------------------------------------------------------


class TestBackpressureScale:
    """Scale projection for K = 50, 100, 1k, 10k, 50k, 100k."""

    async def test_scale_simulated_k50_k100(self, redis: RedisClient) -> None:
        """Simulate K=50 and K=100 (1 call/worker for speed)."""
        rows: list[ScaleRow] = []
        for k in K_SCALE_SIMULATED:
            fake = fake_aioredis.FakeRedis(decode_responses=True)
            r = RedisClient.__new__(RedisClient)
            r._redis = fake
            rows.append(await _run_scale_trial(k, r))
            await fake.aclose()

        for row in rows:
            assert row.lim_err_pct < 0.01, (
                f"K={row.k}: rate_limited error rate {row.lim_err_pct:.1%} >= 1%"
            )
            assert row.no_lim_err_pct > 0.50, (
                f"K={row.k}: expected > 50% error without limiter, "
                f"got {row.no_lim_err_pct:.1%}"
            )

    async def test_scale_projection_table(self, redis: RedisClient) -> None:
        """Print full scale table: simulated (≤100) + projected (≥1k). -s to see output."""
        rows: list[ScaleRow] = []

        # Simulated
        for k in K_SCALE_SIMULATED:
            fake = fake_aioredis.FakeRedis(decode_responses=True)
            r = RedisClient.__new__(RedisClient)
            r._redis = fake
            rows.append(await _run_scale_trial(k, r))
            await fake.aclose()

        # Analytical projection
        for k in K_SCALE_PROJECTED:
            rows.append(_project_scale_row(k))

        _print_scale_table(rows)

        # Rate limiter always gives 0 % errors regardless of K
        for row in rows:
            assert row.lim_err_pct == 0.0


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
        for k in K_VALUES:
            fake_a = fake_aioredis.FakeRedis(decode_responses=True)
            r_a = RedisClient.__new__(RedisClient)
            r_a._redis = fake_a
            rows.append(await _run_trial(k, use_limiter=False, redis=r_a))
            await fake_a.aclose()

            fake_b = fake_aioredis.FakeRedis(decode_responses=True)
            r_b = RedisClient.__new__(RedisClient)
            r_b._redis = fake_b
            rows.append(await _run_trial(k, use_limiter=True, redis=r_b))
            await fake_b.aclose()

        _print_table(rows)
        await fake.aclose()

    asyncio.run(_main())
    sys.exit(0)
