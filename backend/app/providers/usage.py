"""Per-run LLM usage tracking with visual progress."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _StageStats:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_latency_ms: int = 0


@dataclass
class UsageTracker:
    """Accumulates per-stage LLM usage for a single pipeline run."""

    _stages: dict[str, _StageStats] = field(default_factory=dict)

    def record(
        self,
        stage: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> None:
        if stage not in self._stages:
            self._stages[stage] = _StageStats()
        s = self._stages[stage]
        s.requests += 1
        s.input_tokens += input_tokens
        s.output_tokens += output_tokens
        s.total_latency_ms += latency_ms

    @property
    def total_requests(self) -> int:
        return sum(s.requests for s in self._stages.values())

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self._stages.values())

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self._stages.values())

    def stage_stats(self, stage: str) -> dict:
        s = self._stages.get(stage)
        if not s or s.requests == 0:
            return {"requests": 0, "input_tokens": 0, "output_tokens": 0, "avg_latency_ms": 0}
        return {
            "requests": s.requests,
            "input_tokens": s.input_tokens,
            "output_tokens": s.output_tokens,
            "avg_latency_ms": s.total_latency_ms // s.requests,
        }

    def progress(self, stage: str, completed: int, total: int) -> str:
        s = self._stages.get(stage)
        tokens = (s.input_tokens + s.output_tokens) if s else 0
        return f"[{stage}] {completed}/{total} requests ({tokens:,} tokens used)"

    def summary_table(self) -> str:
        header = f"{'Stage':<8} {'Reqs':>6} {'In Tok':>10} {'Out Tok':>10} {'Avg Lat':>10}"
        sep = "-" * len(header)
        lines = [header, sep]

        for stage_name in sorted(self._stages):
            s = self.stage_stats(stage_name)
            avg = f"{s['avg_latency_ms']}ms"
            lines.append(
                f"{stage_name:<8} {s['requests']:>6} "
                f"{s['input_tokens']:>10,} {s['output_tokens']:>10,} "
                f"{avg:>10}"
            )

        total_lat = sum(s.total_latency_ms for s in self._stages.values())
        total_req = self.total_requests
        avg_total = f"{total_lat // total_req}ms" if total_req else "0ms"
        lines.append(sep)
        lines.append(
            f"{'TOTAL':<8} {total_req:>6} "
            f"{self.total_input_tokens:>10,} {self.total_output_tokens:>10,} "
            f"{avg_total:>10}"
        )
        return "\n".join(lines)
