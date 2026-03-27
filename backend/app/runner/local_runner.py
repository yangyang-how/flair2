from datetime import UTC, datetime

import structlog

from app.config import settings
from app.models.performance import VideoPerformance
from app.models.pipeline import PipelineConfig
from app.models.stages import S6Output, VideoInput
from app.pipeline.stages.s1_analyze import s1_analyze
from app.pipeline.stages.s2_aggregate import s2_aggregate
from app.pipeline.stages.s3_generate import s3_generate
from app.pipeline.stages.s4_vote import s4_vote
from app.pipeline.stages.s5_rank import s5_rank
from app.pipeline.stages.s6_personalize import s6_personalize
from app.providers.base import ReasoningProvider

logger = structlog.get_logger()


async def run_pipeline(
    config: PipelineConfig,
    videos: list[VideoInput],
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
    num_scripts: int | None = None,
    num_personas: int | None = None,
    top_n: int | None = None,
) -> S6Output:
    """Run full pipeline locally. No Redis, no Celery.
    Same stage functions as distributed mode.

    Optional params override settings for testing with smaller numbers.
    """
    _num_scripts = num_scripts or settings.s3_script_count
    _num_personas = num_personas or settings.s4_persona_count
    _top_n = top_n or settings.s6_top_n

    logger.info("pipeline_start", run_id=config.run_id, videos=len(videos))

    # S1: Analyze all videos
    logger.info("s1_start", count=len(videos))
    patterns = []
    for i, video in enumerate(videos):
        pattern = await s1_analyze(video, provider)
        patterns.append(pattern)
        logger.info("s1_progress", completed=i + 1, total=len(videos))
    logger.info("s1_complete", patterns=len(patterns))

    # S2: Aggregate
    logger.info("s2_start")
    library = s2_aggregate(patterns)
    logger.info("s2_complete", pattern_types=len(library.patterns))

    # S3: Generate scripts
    logger.info("s3_start", target=_num_scripts)
    scripts = await s3_generate(library, provider, feedback, num_scripts=_num_scripts)
    logger.info("s3_complete", scripts=len(scripts))

    # S4: Vote
    logger.info("s4_start", personas=_num_personas)
    votes = []
    for i in range(_num_personas):
        vote = await s4_vote(scripts, f"persona_{i}", provider, feedback)
        votes.append(vote)
        logger.info("s4_progress", completed=i + 1, total=_num_personas)
    logger.info("s4_complete", votes=len(votes))

    # S5: Rank
    logger.info("s5_start")
    rankings = s5_rank(votes, top_n=_top_n)
    logger.info("s5_complete", top_scripts=[r.script_id for r in rankings.top_10])

    # S6: Personalize top N
    actual_top_n = min(_top_n, len(rankings.top_10))
    logger.info("s6_start", count=actual_top_n)
    results = []
    for ranked in rankings.top_10[:actual_top_n]:
        script = next((s for s in scripts if s.script_id == ranked.script_id), None)
        if script is None:
            logger.warning("script_not_found", script_id=ranked.script_id)
            continue
        result = await s6_personalize(script, config.creator_profile, provider)
        result.rank = ranked.rank
        result.vote_score = ranked.score
        results.append(result)
    logger.info("s6_complete", results=len(results))

    output = S6Output(
        run_id=config.run_id,
        results=results,
        creator_profile=config.creator_profile,
        completed_at=datetime.now(UTC),
    )

    logger.info("pipeline_complete", run_id=config.run_id, results=len(results))
    return output
