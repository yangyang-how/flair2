from app.models.stages import S1Pattern, S2PatternLibrary
from app.pipeline.stages.s2_aggregate import s2_aggregate


def _make_pattern(video_id: str, hook_type: str, pacing: str) -> S1Pattern:
    return S1Pattern(
        video_id=video_id,
        hook_type=hook_type,
        pacing=pacing,
        emotional_arc="curiosity_gap",
        pattern_interrupts=["cut"],
        retention_mechanics=["open loop"],
        engagement_triggers=["relatability"],
        structure_notes="test pattern",
    )


def test_s2_aggregate_groups_by_pattern():
    patterns = [
        _make_pattern("v1", "question", "fast_slow_fast"),
        _make_pattern("v2", "question", "fast_slow_fast"),
        _make_pattern("v3", "shock", "escalating"),
        _make_pattern("v4", "question", "fast_slow_fast"),
    ]
    result = s2_aggregate(patterns)
    assert isinstance(result, S2PatternLibrary)
    assert result.total_videos_analyzed == 4
    assert result.patterns[0].frequency >= result.patterns[1].frequency


def test_s2_aggregate_empty_input():
    result = s2_aggregate([])
    assert result.total_videos_analyzed == 0
    assert len(result.patterns) == 0


def test_s2_aggregate_single_pattern():
    patterns = [_make_pattern("v1", "story", "steady")]
    result = s2_aggregate(patterns)
    assert len(result.patterns) == 1
    assert result.patterns[0].frequency == 1


def test_s2_aggregate_sorted_by_frequency():
    patterns = [
        _make_pattern("v1", "question", "fast"),
        _make_pattern("v2", "shock", "escalating"),
        _make_pattern("v3", "shock", "escalating"),
        _make_pattern("v4", "shock", "escalating"),
        _make_pattern("v5", "question", "fast"),
    ]
    result = s2_aggregate(patterns)
    assert result.patterns[0].pattern_type == "shock + escalating"
    assert result.patterns[0].frequency == 3
    assert result.patterns[1].frequency == 2
