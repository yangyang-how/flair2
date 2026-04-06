"""Celery tasks — thin wrappers around pure stage functions.

Each task:
  1. Deserializes input from JSON
  2. Gets provider for this run from PipelineConfig stored in Redis
  3. Calls the pure stage function
  4. Stores result in Redis (key names follow interface contract #71)
  5. INCRs the done counter (for fan-out stages)
  6. Calls orchestrator.on_sX_complete()

Tasks are sync; async work runs inside asyncio.run().
"""

import asyncio
import json

import structlog

from app.config import settings
from app.infra.redis_client import RedisClient
from app.models.errors import ProviderError, StageError
from app.models.pipeline import PipelineConfig
from app.models.stages import (
    CandidateScript,
    PersonaVote,
    S1Pattern,
    S2PatternLibrary,
    VideoInput,
)
from app.pipeline.stages.s1_analyze import s1_analyze
from app.pipeline.stages.s2_aggregate import s2_aggregate
from app.pipeline.stages.s3_generate import s3_generate
from app.pipeline.stages.s4_vote import s4_vote
from app.pipeline.stages.s5_rank import s5_rank
from app.pipeline.stages.s6_personalize import s6_personalize
from app.providers.registry import get_reasoning_provider
from app.workers.celery_app import celery_app

logger = structlog.get_logger()


def _get_provider(config: PipelineConfig):
    key_map = {
        "gemini": settings.gemini_api_key,
        "kimi": settings.kimi_api_key,
        "openai": settings.openai_api_key,
    }
    return get_reasoning_provider(
        config.reasoning_model, api_key=key_map.get(config.reasoning_model, "")
    )


async def _load_config(redis: RedisClient, run_id: str) -> PipelineConfig:
    raw = await redis.get(f"run:{run_id}:config")
    return PipelineConfig.model_validate_json(raw)


# ---------------------------------------------------------------------------
# S1 — analyze one video
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, default_retry_delay=4)
def s1_analyze_task(self, run_id: str, video_json: str):
    async def _run():
        redis = RedisClient(settings.redis_url)
        try:
            config = await _load_config(redis, run_id)
            video = VideoInput.model_validate_json(video_json)
            provider = _get_provider(config)

            pattern = await s1_analyze(video, provider)
            await redis.set(f"result:s1:{run_id}:{video.video_id}", pattern.model_dump_json())

            from app.pipeline.orchestrator import Orchestrator
            await Orchestrator(redis).on_s1_complete(run_id, video.video_id)
        finally:
            await redis.aclose()

    try:
        asyncio.run(_run())
    except ProviderError as exc:
        raise self.retry(exc=exc) from exc
    except StageError:
        raise


# ---------------------------------------------------------------------------
# S2 — aggregate all S1 patterns (single task, reads all results)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, default_retry_delay=4)
def s2_aggregate_task(self, run_id: str):
    async def _run():
        redis = RedisClient(settings.redis_url)
        try:
            pattern_keys = await redis.keys(f"result:s1:{run_id}:*")
            patterns: list[S1Pattern] = []
            for key in pattern_keys:
                raw = await redis.get(key)
                patterns.append(S1Pattern.model_validate_json(raw))

            library = s2_aggregate(patterns)
            await redis.set(f"pattern_library:{run_id}", library.model_dump_json())

            from app.pipeline.orchestrator import Orchestrator
            await Orchestrator(redis).on_s2_complete(run_id, len(library.patterns))
        finally:
            await redis.aclose()

    try:
        asyncio.run(_run())
    except StageError:
        raise


# ---------------------------------------------------------------------------
# S3 — generate candidate scripts (sequential)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, default_retry_delay=4)
def s3_generate_task(self, run_id: str):
    async def _run():
        redis = RedisClient(settings.redis_url)
        try:
            config = await _load_config(redis, run_id)
            raw = await redis.get(f"pattern_library:{run_id}")
            library = S2PatternLibrary.model_validate_json(raw)
            provider = _get_provider(config)

            scripts = await s3_generate(library, provider, num_scripts=config.num_scripts)
            await redis.set(
                f"scripts:candidates:{run_id}",
                json.dumps([s.model_dump() for s in scripts]),
            )

            from app.pipeline.orchestrator import Orchestrator
            await Orchestrator(redis).on_s3_complete(run_id)
        finally:
            await redis.aclose()

    try:
        asyncio.run(_run())
    except ProviderError as exc:
        raise self.retry(exc=exc) from exc
    except StageError:
        raise


# ---------------------------------------------------------------------------
# S4 — one persona votes
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, default_retry_delay=4)
def s4_vote_task(self, run_id: str, persona_id: str):
    async def _run():
        redis = RedisClient(settings.redis_url)
        try:
            config = await _load_config(redis, run_id)
            raw = await redis.get(f"scripts:candidates:{run_id}")
            scripts = [CandidateScript(**s) for s in json.loads(raw)]
            provider = _get_provider(config)

            vote = await s4_vote(scripts, persona_id, provider)
            await redis.set(f"result:s4:{run_id}:{persona_id}", vote.model_dump_json())

            from app.pipeline.orchestrator import Orchestrator
            await Orchestrator(redis).on_s4_complete(run_id, persona_id, vote.top_5_script_ids)
        finally:
            await redis.aclose()

    try:
        asyncio.run(_run())
    except ProviderError as exc:
        raise self.retry(exc=exc) from exc
    except StageError:
        raise


# ---------------------------------------------------------------------------
# S5 — rank all votes (single task)
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, default_retry_delay=4)
def s5_rank_task(self, run_id: str):
    async def _run():
        redis = RedisClient(settings.redis_url)
        try:
            config = await _load_config(redis, run_id)
            vote_keys = await redis.keys(f"result:s4:{run_id}:*")
            votes: list[PersonaVote] = []
            for key in vote_keys:
                raw = await redis.get(key)
                votes.append(PersonaVote.model_validate_json(raw))

            rankings = s5_rank(votes, top_n=config.top_n)
            await redis.set(f"top_scripts:{run_id}", rankings.model_dump_json())

            from app.pipeline.orchestrator import Orchestrator
            await Orchestrator(redis).on_s5_complete(run_id)
        finally:
            await redis.aclose()

    try:
        asyncio.run(_run())
    except StageError:
        raise


# ---------------------------------------------------------------------------
# S6 — personalize one top script
# ---------------------------------------------------------------------------

@celery_app.task(bind=True, max_retries=3, default_retry_delay=4)
def s6_personalize_task(self, run_id: str, script_id: str):
    async def _run():
        redis = RedisClient(settings.redis_url)
        try:
            config = await _load_config(redis, run_id)

            # Find the candidate script
            raw_scripts = await redis.get(f"scripts:candidates:{run_id}")
            candidates = [CandidateScript(**s) for s in json.loads(raw_scripts)]
            script = next((s for s in candidates if s.script_id == script_id), None)
            if script is None:
                raise StageError(f"S6: script {script_id} not found in candidates", stage="S6")

            # Get rank/score from S5 rankings
            from app.models.stages import S5Rankings
            raw_rankings = await redis.get(f"top_scripts:{run_id}")
            rankings = S5Rankings.model_validate_json(raw_rankings)
            ranked = next((r for r in rankings.top_10 if r.script_id == script_id), None)

            provider = _get_provider(config)
            result = await s6_personalize(script, config.creator_profile, provider)

            if ranked is not None:
                result.rank = ranked.rank
                result.vote_score = ranked.score

            await redis.set(f"result:s6:{run_id}:{script_id}", result.model_dump_json())

            from app.pipeline.orchestrator import Orchestrator
            await Orchestrator(redis).on_s6_complete(run_id, script_id)
        finally:
            await redis.aclose()

    try:
        asyncio.run(_run())
    except ProviderError as exc:
        raise self.retry(exc=exc) from exc
    except StageError:
        raise
