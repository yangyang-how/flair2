from app.models.stages import PersonaVote, S5Rankings
from app.pipeline.stages.s5_rank import s5_rank


def test_s5_rank_aggregates_votes():
    votes = [
        PersonaVote(
            persona_id=f"persona_{i}",
            persona_description="test",
            top_5_script_ids=[
                "script_001",
                "script_003",
                "script_005",
                "script_007",
                "script_009",
            ],
            reasoning="test",
        )
        for i in range(60)
    ] + [
        PersonaVote(
            persona_id=f"persona_{i + 60}",
            persona_description="test",
            top_5_script_ids=[
                "script_002",
                "script_004",
                "script_006",
                "script_008",
                "script_001",
            ],
            reasoning="test",
        )
        for i in range(40)
    ]
    result = s5_rank(votes)
    assert isinstance(result, S5Rankings)
    assert len(result.top_10) == 9  # 9 unique scripts in test data
    assert result.top_10[0].rank == 1
    assert result.total_votes_cast == 100
    # script_001 appears in all 100 votes, should be ranked highest
    assert result.top_10[0].script_id == "script_001"


def test_s5_rank_scores_descending():
    votes = [
        PersonaVote(
            persona_id=f"p_{i}",
            persona_description="test",
            top_5_script_ids=["s1", "s2", "s3", "s4", "s5"],
            reasoning="test",
        )
        for i in range(10)
    ]
    result = s5_rank(votes)
    scores = [r.score for r in result.top_10]
    assert scores == sorted(scores, reverse=True)


def test_s5_rank_weighted_scoring():
    """1st pick = 5pts, 2nd = 4pts, etc. Verify weighting works."""
    votes = [
        PersonaVote(
            persona_id="p_0",
            persona_description="test",
            top_5_script_ids=["s_first", "s_second", "s_third", "s_fourth", "s_fifth"],
            reasoning="test",
        ),
    ]
    result = s5_rank(votes)
    first = next(r for r in result.top_10 if r.script_id == "s_first")
    fifth = next(r for r in result.top_10 if r.script_id == "s_fifth")
    assert first.score > fifth.score
