from collections import Counter

from app.models.stages import PersonaVote, RankedScript, S5Rankings

DEFAULT_TOP_N = 10


def s5_rank(votes: list[PersonaVote], top_n: int = DEFAULT_TOP_N) -> S5Rankings:
    """Aggregate votes into ranked top N. No LLM — pure algorithmic.

    Scoring: Each vote position gets a weighted score.
    1st pick = 5pts, 2nd = 4pts, 3rd = 3pts, 4th = 2pts, 5th = 1pt.
    Mirrors TikTok's engagement weighting (rewatch > completion > share > comment > like).
    """
    score_weights = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1}
    scores: Counter[str] = Counter()
    vote_counts: Counter[str] = Counter()

    for vote in votes:
        for position, script_id in enumerate(vote.top_5_script_ids):
            scores[script_id] += score_weights.get(position, 1)
            vote_counts[script_id] += 1

    top_scripts = scores.most_common(top_n)

    ranked = [
        RankedScript(
            script_id=script_id,
            vote_count=vote_counts[script_id],
            score=float(score),
            rank=rank + 1,
        )
        for rank, (script_id, score) in enumerate(top_scripts)
    ]

    return S5Rankings(
        top_10=ranked,
        total_votes_cast=len(votes),
    )
