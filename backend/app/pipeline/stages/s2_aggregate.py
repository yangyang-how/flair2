from collections import defaultdict

from app.models.stages import PatternEntry, S1Pattern, S2PatternLibrary


def s2_aggregate(patterns: list[S1Pattern]) -> S2PatternLibrary:
    """Merge N patterns into a ranked library. No LLM — pure algorithmic."""
    if not patterns:
        return S2PatternLibrary(patterns=[], total_videos_analyzed=0)

    groups: dict[str, list[S1Pattern]] = defaultdict(list)
    for p in patterns:
        key = f"{p.hook_type} + {p.pacing}"
        groups[key].append(p)

    entries = []
    for key, group in groups.items():
        entries.append(
            PatternEntry(
                pattern_type=key,
                frequency=len(group),
                examples=[p.video_id for p in group[:5]],
                avg_engagement=0.0,
            )
        )

    entries.sort(key=lambda e: e.frequency, reverse=True)

    return S2PatternLibrary(
        patterns=entries,
        total_videos_analyzed=len(patterns),
    )
