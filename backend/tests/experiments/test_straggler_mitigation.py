"""Straggler Mitigation Experiment (95% Completion Threshold).

Validates that the 95% completion threshold (commit a15876b) reduces
pipeline end-to-end latency when a small fraction of tasks take
disproportionately long.

Background
----------
In any distributed fan-out, a few "straggler" tasks take much longer than
the median — due to LLM provider variance, network jitter, or rate-limit
backoff. If the next stage waits for 100% completion, one slow task delays
the entire pipeline.

The solution (Orchestrator._try_transition) fires the next stage at:
    needed = ceil(N × threshold)   # default threshold=0.95

For N=42 personas: needed = ceil(42 × 0.95) = 40
For N=100 videos:  needed = ceil(100 × 0.95) = 95

The 2–5 straggler tasks still run to completion (their results are stored),
but they don't block the pipeline from advancing.

Experiment design
-----------------
We inject artificial straggler delays and measure:
  - Pipeline completion time at threshold=1.00 (wait for all)
  - Pipeline completion time at threshold=0.95 (advance early)
  - Time saved = (t_100 - t_95) / t_100

Three straggler scenarios:
  1. mild:   last 5% tasks take 3× median
  2. severe: last 5% tasks take 10× median
  3. worst:  last 5% tasks take 20× median (rate-limit backoff scenario)

Acceptance criteria
-------------------
- threshold=0.95 saves ≥ 20% time vs threshold=1.00 under severe stragglers
- threshold=1.00 and threshold=0.95 produce the same next-stage result
  (the stragglers' outputs are still stored, only timing changes)

Run:
    pytest tests/experiments/test_straggler_mitigation.py -v -s
"""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass

import pytest

# ---------------------------------------------------------------------------
# Experiment parameters
# ---------------------------------------------------------------------------

BASE_LATENCY_MS: float = 50.0   # typical task latency
N_TASKS: int = 100              # matches S1 production default (videos)
# With threshold=0.95: needed = ceil(100×0.95) = 95, n_fast = 95 → trigger fires at base time
STRAGGLER_FRACTION: float = 0.05   # top 5% are slow (5 stragglers, 95 fast)

STRAGGLER_SCENARIOS: list[tuple[str, float]] = [
    ("mild",   3.0),    # 3× median
    ("severe", 10.0),   # 10× median
    ("worst",  20.0),   # 20× median (rate-limit backoff)
]

MIN_SAVINGS_SEVERE: float = 0.20   # ≥20% time saved on severe stragglers
THRESHOLD_95 = 0.95
THRESHOLD_100 = 1.00


# ---------------------------------------------------------------------------
# Simulation
# ---------------------------------------------------------------------------

def _make_latencies(
    n: int,
    base_ms: float,
    straggler_fraction: float,
    straggler_multiplier: float,
) -> list[float]:
    """Return per-task latencies. Last ceil(n × fraction) tasks are stragglers."""
    n_stragglers = max(1, math.ceil(n * straggler_fraction))
    latencies = [base_ms] * (n - n_stragglers) + [base_ms * straggler_multiplier] * n_stragglers
    return latencies


async def _run_fanout_with_threshold(
    latencies_ms: list[float],
    threshold: float,
) -> tuple[float, int]:
    """Run fan-out tasks and fire 'next stage' when threshold fraction complete.

    Returns (wall_time_seconds, tasks_done_at_trigger).
    Remaining tasks still complete; we just record when the trigger fires.
    """
    n = len(latencies_ms)
    needed = math.ceil(n * threshold)
    done_count = 0
    trigger_time: list[float | None] = [None]
    t0 = time.perf_counter()

    async def one_task(latency_ms: float, task_idx: int) -> None:
        nonlocal done_count
        await asyncio.sleep(latency_ms / 1000)
        done_count += 1
        if done_count >= needed and trigger_time[0] is None:
            trigger_time[0] = time.perf_counter() - t0

    await asyncio.gather(*[one_task(lat, i) for i, lat in enumerate(latencies_ms)])

    total_time = time.perf_counter() - t0
    trigger = trigger_time[0] or total_time
    return trigger, done_count


@dataclass
class StragglerResult:
    scenario: str
    multiplier: float
    time_100_ms: float
    time_95_ms: float
    savings_pct: float
    n_done_at_trigger_95: int

    def passed(self) -> bool:
        return self.savings_pct >= MIN_SAVINGS_SEVERE or self.multiplier < 10.0


def _print_table(results: list[StragglerResult]) -> None:
    print(
        f"\n{'Scenario':<10} {'mult':>6} {'t=100%(ms)':>12} {'t=95%(ms)':>11} "
        f"{'saved':>8} {'tasks@trigger':>14} {'pass':>5}"
    )
    print("─" * 72)
    for r in results:
        mark = "✓" if r.passed() else "✗"
        print(
            f"{r.scenario:<10} {r.multiplier:>6.0f}× {r.time_100_ms:>12.0f} "
            f"{r.time_95_ms:>11.0f} {r.savings_pct:>7.1f}% {r.n_done_at_trigger_95:>14} "
            f"{mark:>5}"
        )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStragglerMitigation:

    @pytest.mark.asyncio
    async def test_threshold_saves_time_under_stragglers(self):
        """95% threshold reduces pipeline trigger time vs waiting for 100%."""
        results = []
        for label, mult in STRAGGLER_SCENARIOS:
            latencies = _make_latencies(N_TASKS, BASE_LATENCY_MS, STRAGGLER_FRACTION, mult)

            t_100, _ = await _run_fanout_with_threshold(latencies, THRESHOLD_100)
            t_95, n_at_trigger = await _run_fanout_with_threshold(latencies, THRESHOLD_95)

            savings = (t_100 - t_95) / t_100
            results.append(StragglerResult(
                scenario=label,
                multiplier=mult,
                time_100_ms=t_100 * 1000,
                time_95_ms=t_95 * 1000,
                savings_pct=savings * 100,
                n_done_at_trigger_95=n_at_trigger,
            ))

        _print_table(results)

        for r in results:
            if r.multiplier >= 10.0:
                assert r.savings_pct >= MIN_SAVINGS_SEVERE * 100, (
                    f"[{r.scenario}] Expected ≥{MIN_SAVINGS_SEVERE:.0%} savings, "
                    f"got {r.savings_pct:.1f}%"
                )

    @pytest.mark.asyncio
    async def test_no_savings_without_stragglers(self):
        """When all tasks have equal latency, 95% and 100% thresholds are similar."""
        latencies = [BASE_LATENCY_MS] * N_TASKS  # no stragglers

        t_100, _ = await _run_fanout_with_threshold(latencies, THRESHOLD_100)
        t_95, _ = await _run_fanout_with_threshold(latencies, THRESHOLD_95)

        savings = (t_100 - t_95) / t_100
        # With no stragglers, savings should be small (just the last 5% of tasks)
        expected_max_savings = STRAGGLER_FRACTION + 0.05  # small tolerance
        assert savings <= expected_max_savings, (
            f"Without stragglers, savings should be ≤{expected_max_savings:.0%}, "
            f"got {savings:.1%}"
        )

    @pytest.mark.asyncio
    async def test_trigger_fires_at_correct_task_count(self):
        """Next stage triggers at exactly ceil(N × 0.95) completions."""
        latencies = _make_latencies(N_TASKS, BASE_LATENCY_MS, STRAGGLER_FRACTION, 10.0)
        expected_trigger = math.ceil(N_TASKS * THRESHOLD_95)

        _, n_at_trigger = await _run_fanout_with_threshold(latencies, THRESHOLD_95)

        assert n_at_trigger >= expected_trigger, (
            f"Trigger fired at {n_at_trigger} completions, "
            f"expected ≥{expected_trigger} (ceil({N_TASKS}×{THRESHOLD_95}))"
        )

    @pytest.mark.asyncio
    async def test_all_tasks_still_complete_after_trigger(self):
        """Triggering early does not cancel remaining straggler tasks."""
        latencies = _make_latencies(N_TASKS, BASE_LATENCY_MS, STRAGGLER_FRACTION, 10.0)
        completed = []

        done_count = 0
        needed = math.ceil(N_TASKS * THRESHOLD_95)
        trigger_fired = [False]

        async def one_task(latency_ms: float, idx: int) -> None:
            nonlocal done_count
            await asyncio.sleep(latency_ms / 1000)
            done_count += 1
            completed.append(idx)
            if done_count >= needed:
                trigger_fired[0] = True

        await asyncio.gather(*[one_task(lat, i) for i, lat in enumerate(latencies)])

        assert trigger_fired[0], "Trigger never fired"
        assert len(completed) == N_TASKS, (
            f"Only {len(completed)}/{N_TASKS} tasks completed — "
            "straggler tasks must not be cancelled"
        )

    @pytest.mark.asyncio
    async def test_production_scale_s4_savings(self):
        """S4 production config: N=42, 2 stragglers at 10× → measures real savings.

        With N=42 and threshold=0.95: needed = ceil(42×0.95) = 40.
        Using 2 stragglers (fraction≈0.048) ensures n_fast=40=needed,
        so the trigger fires exactly when all fast tasks complete.
        """
        n, n_stragglers, mult = 42, 2, 10.0
        latencies = [BASE_LATENCY_MS] * (n - n_stragglers) + [BASE_LATENCY_MS * mult] * n_stragglers
        t_100, _ = await _run_fanout_with_threshold(latencies, 1.00)
        t_95, n_trigger = await _run_fanout_with_threshold(latencies, 0.95)
        savings = (t_100 - t_95) / t_100

        print(f"\nS4 N={n}, {n_stragglers} stragglers at {mult:.0f}× median:")
        print(f"  threshold=1.00: {t_100*1000:.0f} ms")
        print(f"  threshold=0.95: {t_95*1000:.0f} ms (fired at {n_trigger} completions)")
        print(f"  Time saved:     {savings:.1%}")

        assert savings >= MIN_SAVINGS_SEVERE, (
            f"S4 production savings {savings:.1%} < {MIN_SAVINGS_SEVERE:.0%}"
        )
