"""Generate charts from pipeline test run data for course report."""

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import numpy as np
from pathlib import Path

# Output directory
OUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "charts"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Consistent style
COLORS = {
    "input": "#4A90D9",
    "output": "#E8734A",
    "completed": "#4CAF50",
    "remaining": "#D0D0D0",
    "timing": "#5B7FA5",
}
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})


def chart_token_usage() -> None:
    """Chart 1: Token usage by pipeline stage (grouped bar)."""
    stages = ["S1\nDiscover", "S3\nStudio Brief", "S4\nVideo Brief", "S6\nEvaluate"]
    input_tokens = [1193, 259, 1731, 673]
    output_tokens = [3945, 1131, 4691, 5347]
    requests = [2, 1, 3, 2]

    x = np.arange(len(stages))
    width = 0.32

    fig, ax = plt.subplots(figsize=(9, 5))
    bars_in = ax.bar(x - width / 2, input_tokens, width, label="Input tokens",
                     color=COLORS["input"], edgecolor="white", linewidth=0.5)
    bars_out = ax.bar(x + width / 2, output_tokens, width, label="Output tokens",
                      color=COLORS["output"], edgecolor="white", linewidth=0.5)

    # Annotate with request counts
    for i, (bi, bo) in enumerate(zip(bars_in, bars_out)):
        ax.text(bi.get_x() + bi.get_width() / 2, bi.get_height() + 80,
                f"{input_tokens[i]:,}", ha="center", va="bottom", fontsize=8, color="#555")
        ax.text(bo.get_x() + bo.get_width() / 2, bo.get_height() + 80,
                f"{output_tokens[i]:,}", ha="center", va="bottom", fontsize=8, color="#555")
        # Request count label below stage name
        ax.text(x[i], -900, f"({requests[i]} req)", ha="center", fontsize=8, color="#888")

    ax.set_ylabel("Tokens")
    ax.set_title("LLM Token Usage by Pipeline Stage", fontsize=14, fontweight="bold", pad=15)
    ax.set_xticks(x)
    ax.set_xticklabels(stages, fontsize=10)
    ax.yaxis.set_major_formatter(ticker.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.legend(frameon=False, loc="upper left")
    ax.set_ylim(-1000, 6500)

    fig.tight_layout()
    fig.savefig(OUT_DIR / "token_usage_by_stage.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUT_DIR / 'token_usage_by_stage.png'}")


def chart_pipeline_timing() -> None:
    """Chart 2: Pipeline stage duration (horizontal bar)."""
    stages = ["S1 — Discover", "S2 — Curate", "S3 — Studio Brief",
              "S4 — Video Brief", "S5 — Assemble", "S6 — Evaluate"]
    durations = [78, 0.5, 75, 120, 0.5, 146]

    fig, ax = plt.subplots(figsize=(9, 4.5))
    y = np.arange(len(stages))
    bars = ax.barh(y, durations, height=0.55, color=COLORS["timing"],
                   edgecolor="white", linewidth=0.5)

    # Annotate each bar
    for i, (bar, d) in enumerate(zip(bars, durations)):
        label = f"{d:.0f}s" if d >= 1 else "<1s"
        x_pos = bar.get_width() + 3
        ax.text(x_pos, bar.get_y() + bar.get_height() / 2, label,
                va="center", fontsize=10, fontweight="bold", color="#333")

    ax.set_yticks(y)
    ax.set_yticklabels(stages, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("Duration (seconds)")
    ax.set_title("Pipeline Stage Duration (2-video test run)", fontsize=14,
                 fontweight="bold", pad=15)
    ax.set_xlim(0, 175)

    # Total annotation
    total = sum(durations)
    ax.text(0.98, 0.02, f"Total: {total:.0f}s (~{total/60:.1f} min)",
            transform=ax.transAxes, ha="right", va="bottom",
            fontsize=10, color="#666", fontstyle="italic")

    fig.tight_layout()
    fig.savefig(OUT_DIR / "pipeline_timing.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUT_DIR / 'pipeline_timing.png'}")


def chart_milestone_progress() -> None:
    """Chart 3: Project milestone progress (horizontal stacked bar)."""
    milestones = [
        "M1 — MVP Pipeline",
        "M2 — AWS Infra",
        "M3 — Distributed",
        "M4 — Frontend",
        "M5 — Experiments",
    ]
    closed = [7, 6, 0, 0, 1]
    total = [8, 6, 5, 7, 4]
    remaining = [t - c for t, c in zip(total, closed)]
    pcts = [c / t * 100 for c, t in zip(closed, total)]

    fig, ax = plt.subplots(figsize=(9, 4))
    y = np.arange(len(milestones))
    height = 0.5

    ax.barh(y, closed, height=height, color=COLORS["completed"],
            edgecolor="white", linewidth=0.5, label="Closed")
    ax.barh(y, remaining, height=height, left=closed, color=COLORS["remaining"],
            edgecolor="white", linewidth=0.5, label="Remaining")

    # Annotate with fraction and percentage
    for i in range(len(milestones)):
        label = f"{closed[i]}/{total[i]}  ({pcts[i]:.0f}%)"
        ax.text(total[i] + 0.2, y[i], label, va="center", fontsize=10, color="#333")

    ax.set_yticks(y)
    ax.set_yticklabels(milestones, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel("Issues")
    ax.set_title("Milestone Progress \u2014 March 28, 2026", fontsize=14,
                 fontweight="bold", pad=15)
    ax.set_xlim(0, 10)
    ax.xaxis.set_major_locator(ticker.MaxNLocator(integer=True))
    ax.legend(frameon=False, loc="lower right")

    fig.tight_layout()
    fig.savefig(OUT_DIR / "milestone_progress.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved: {OUT_DIR / 'milestone_progress.png'}")


if __name__ == "__main__":
    chart_token_usage()
    chart_pipeline_timing()
    chart_milestone_progress()
    print("\nAll charts generated.")
