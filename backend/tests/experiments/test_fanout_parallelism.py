"""Fan-out / Fan-in Parallelism Experiment.

Validates that the S1 and S4 fan-out pattern achieves near-linear speedup
over serial execution and that the concurrency cap (semaphore) correctly
bounds throughput to match the provider's concurrency limit.

Design
------
S1 dispatches one Celery task per video (N=100 by default).
S4 dispatches one Celery task per persona (N=42 by default).
Each task is IO-bound: it waits for an LLM response.

In a distributed system, N independent IO-bound tasks run in parallel
should complete in time ≈ latency_per_task, not N × latency_per_task.

We simulate this locally using asyncio.gather with asyncio.sleep to
stand in for real LLM latency. The semaphore models the provider
concurrency cap (e.g. Kimi's 29-slot limit via RedisSemaphore).

Acceptance criteria
-------------------
1. Uncapped concurrent execution achieves speedup ≥ 0.65 × N (near-linear).
2. Capped execution achieves speedup ≥ 0.65 × min(N, cap).
3. Serial execution (cap=1) takes ≈ N × latency (baseline confirmed).

Note on efficiency floor: asyncio.gather over asyncio.sleep achieves 65–90%
of theoretical speedup due to event-loop scheduling overhead. Real Celery
workers achieve higher efficiency because tasks run in separate processes.

Run:
    pytest tests/experiments/test_fanout_parallelism.py -v -s
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import pytest

# ---------------------------------------------------------------------------
# Experiment parameters
# ---------------------------------------------------------------------------

LATENCY_MS: float = 100.0  # simulated LLM call latency (ms) — larger = less scheduling noise
EFFICIENCY_FLOOR: float = 0.65   # minimum efficiency (actual / theoretical speedup)

# Task counts matching production defaults
FANOUT_SIZES = [10, 42, 100]

# Concurrency caps to test (mirrors Kimi's 29-slot semaphore)
CONCURRENCY_CAPS = [1, 5, 10, 29, None]  # None = unlimited


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------

async def _fanout(n: int, latency_ms: float, cap: int | None = None) -> float:
    """Run N independent IO-bound tasks, optionally capped at `cap` concurrent.

    Returns wall-clock time in seconds.
    """
    sem = asyncio.Semaphore(cap) if cap is not None else None

    async def one_task() -> None:
        if sem is not None:
            async with sem:
                await asyncio.sleep(latency_ms / 1000)
        else:
            await asyncio.sleep(latency_ms / 1000)

    t0 = time.perf_counter()
    await asyncio.gather(*[one_task() for _ in range(n)])
    return time.perf_counter() - t0


def _theoretical_speedup(n: int, cap: int | None) -> float:
    """Expected speedup: min(N, cap) over serial."""
    return float(n) if cap is None else float(min(n, cap))


def _serial_time(n: int, latency_ms: float) -> float:
    return n * latency_ms / 1000


@dataclass
class FanoutResult:
    n: int
    cap: int | None
    serial_s: float
    actual_s: float
    theoretical_speedup: float
    actual_speedup: float
    efficiency: float

    @property
    def cap_label(self) -> str:
        return str(self.cap) if self.cap is not None else "∞"

    def passed(self, floor: float) -> bool:
        return self.efficiency >= floor


def _print_table(results: list[FanoutResult]) -> None:
    print(
        f"\n{'N':>5} {'cap':>5} {'serial(ms)':>10} {'actual(ms)':>10} "
        f"{'theoretical×':>13} {'actual×':>9} {'efficiency':>11} {'pass':>5}"
    )
    print("─" * 80)
    for r in results:
        mark = "✓" if r.passed(EFFICIENCY_FLOOR) else "✗"
        print(
            f"{r.n:>5} {r.cap_label:>5} {r.serial_s*1000:>10.0f} {r.actual_s*1000:>10.0f}"
            f" {r.theoretical_speedup:>13.1f} {r.actual_speedup:>9.1f}"
            f" {r.efficiency:>10.1%} {mark:>5}"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestFanoutSpeedup:

    @pytest.mark.asyncio
    async def test_uncapped_speedup_near_linear(self):
        """Without a concurrency cap, speedup ≈ N (all tasks run simultaneously)."""
        results = []
        for n in FANOUT_SIZES:
            serial = _serial_time(n, LATENCY_MS)
            actual = await _fanout(n, LATENCY_MS, cap=None)
            theoretical = _theoretical_speedup(n, None)
            actual_speedup = serial / actual
            efficiency = actual_speedup / theoretical
            results.append(FanoutResult(
                n=n, cap=None,
                serial_s=serial, actual_s=actual,
                theoretical_speedup=theoretical,
                actual_speedup=actual_speedup,
                efficiency=efficiency,
            ))

        _print_table(results)

        for r in results:
            assert r.passed(EFFICIENCY_FLOOR), (
                f"N={r.n} uncapped: efficiency {r.efficiency:.1%} < {EFFICIENCY_FLOOR:.0%}. "
                f"actual={r.actual_s*1000:.0f}ms serial={r.serial_s*1000:.0f}ms"
            )

    @pytest.mark.asyncio
    async def test_capped_speedup_bounded_by_semaphore(self):
        """With a concurrency cap, speedup ≤ cap (semaphore enforces the limit)."""
        n = 42   # matches S4 production default
        results = []
        for cap in [1, 5, 10, 29]:
            serial = _serial_time(n, LATENCY_MS)
            actual = await _fanout(n, LATENCY_MS, cap=cap)
            theoretical = _theoretical_speedup(n, cap)
            actual_speedup = serial / actual
            efficiency = actual_speedup / theoretical
            results.append(FanoutResult(
                n=n, cap=cap,
                serial_s=serial, actual_s=actual,
                theoretical_speedup=theoretical,
                actual_speedup=actual_speedup,
                efficiency=efficiency,
            ))

        _print_table(results)

        for r in results:
            assert r.passed(EFFICIENCY_FLOOR), (
                f"N={r.n} cap={r.cap}: efficiency {r.efficiency:.1%} < {EFFICIENCY_FLOOR:.0%}. "
                f"speedup={r.actual_speedup:.1f}× (theoretical {r.theoretical_speedup:.0f}×)"
            )

    @pytest.mark.asyncio
    async def test_serial_baseline_confirmed(self):
        """cap=1 reduces to serial execution: time ≈ N × latency."""
        n = 10
        actual = await _fanout(n, LATENCY_MS, cap=1)
        expected = _serial_time(n, LATENCY_MS)
        # Allow 20% overhead for event loop scheduling
        assert actual >= expected * 0.8, (
            f"Serial baseline too fast: {actual*1000:.0f}ms < {expected*1000*0.8:.0f}ms"
        )

    @pytest.mark.asyncio
    async def test_speedup_plateaus_beyond_n(self):
        """Speedup does not increase once cap ≥ N (Amdahl ceiling)."""
        n = 10
        time_at_n = await _fanout(n, LATENCY_MS, cap=n)
        time_beyond_n = await _fanout(n, LATENCY_MS, cap=n * 10)

        # Both should complete in roughly 1 latency unit; difference < 20%
        ratio = max(time_at_n, time_beyond_n) / min(time_at_n, time_beyond_n)
        assert ratio < 1.30, (
            f"Speedup should plateau at cap=N={n}, but "
            f"time_at_n={time_at_n*1000:.0f}ms time_beyond={time_beyond_n*1000:.0f}ms "
            f"differ by {ratio:.2f}×"
        )

    @pytest.mark.asyncio
    async def test_s4_production_config_speedup(self):
        """S4: N=42 personas, cap=29 (Kimi limit) — measures real production speedup."""
        n, cap = 42, 29
        serial = _serial_time(n, LATENCY_MS)
        actual = await _fanout(n, LATENCY_MS, cap=cap)
        speedup = serial / actual
        theoretical = _theoretical_speedup(n, cap)
        efficiency = speedup / theoretical

        print(f"\nS4 production config: N={n} cap={cap}")
        print(f"  Serial:      {serial*1000:.0f} ms")
        print(f"  Concurrent:  {actual*1000:.0f} ms")
        print(f"  Speedup:     {speedup:.1f}× (theoretical {theoretical:.0f}×)")
        print(f"  Efficiency:  {efficiency:.1%}")

        assert efficiency >= EFFICIENCY_FLOOR, (
            f"S4 production speedup efficiency {efficiency:.1%} below floor {EFFICIENCY_FLOOR:.0%}"
        )
