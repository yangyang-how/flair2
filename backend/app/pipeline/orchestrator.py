"""Orchestrator — pipeline state machine.

Single writer to the SSE stream (sse:{run_id}) and all stage/status keys.
Workers call on_sX_complete() callbacks; the orchestrator decides when to
transition and dispatches the next batch of tasks.

Follows interface contract #71 v3 exactly:
  - Redis keys:     Section 1
  - SSE events:     Section 2
  - Counter init:   Section 1 (DELETE + SET "0" on start)
  - TTL policy:     Section 1 (24h after terminal state)
  - SSE transport:  XADD / XREAD (not BLPOP)
"""

import json
import math
from datetime import UTC, datetime

import structlog

from app.infra.redis_client import RedisClient
from app.models.pipeline import PipelineConfig
from app.models.stages import FinalResult, S5Rankings, S6Output, VideoInput

logger = structlog.get_logger()

TTL_SECONDS = 86400  # 24 hours


class Orchestrator:
    def __init__(self, redis: RedisClient):
        self._r = redis

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, run_id: str, config: PipelineConfig, videos: list[VideoInput]) -> None:
        """Initialize run state and dispatch S1 fan-out tasks."""
        # Persist config (source of truth for all tasks)
        await self._r.set(f"run:{run_id}:config", config.model_dump_json())
        await self._r.set(f"run:{run_id}:status", "running")
        await self._r.set(f"run:{run_id}:stage", "S1_MAP")

        # Initialize counters — DELETE first to clear stale data from failed reruns
        for key in [
            f"run:{run_id}:s1:done",
            f"run:{run_id}:s4:done",
            f"run:{run_id}:s6:done",
        ]:
            await self._r.delete(key)
            await self._r.set(key, "0")

        await self._xadd_event(run_id, "pipeline_started", {
            "run_id": run_id,
            "total_videos": len(videos),
            "total_personas": config.num_personas,
            "top_n": config.top_n,
        })
        await self._xadd_event(run_id, "stage_started", {
            "stage": "S1_MAP",
            "total_items": len(videos),
        })

        from app.workers.tasks import s1_analyze_task
        for video in videos:
            s1_analyze_task.delay(run_id, video.model_dump_json())
        logger.info("orchestrator_s1_dispatched", run_id=run_id, count=len(videos))

    async def emit_event(self, run_id: str, event: str, data: dict) -> None:
        await self._xadd_event(run_id, event, data)

    async def _try_transition(
        self,
        run_id: str,
        stage_key: str,
        done: int,
        total: int,
        threshold: float,
        transition: "callable",
    ) -> None:
        """Trigger the next-stage transition at most once, when enough tasks
        have finished.

        Uses SETNX on a per-stage flag to guarantee exactly-once dispatch
        even when multiple concurrent completions all cross the threshold
        line within the same millisecond window.

        threshold is a fraction of `total`. 1.0 means "wait for everyone",
        0.95 means "good enough at 95 of 100 — late ones keep running but
        we move on".
        """
        from app.config import settings as _settings  # local: avoid cycle

        # ceil so that threshold=0.95 × 10 items requires 10 completions
        # (not 9 — int() would truncate). Threshold only kicks in for
        # large fan-outs where saving the last 5% actually matters.
        needed = max(1, math.ceil(total * threshold))
        if done < needed and done < total:
            return

        triggered = await self._r.setnx(
            f"run:{run_id}:{stage_key}:triggered", "1", ttl=TTL_SECONDS,
        )
        if not triggered:
            return  # another completion already fired the transition
        logger.info(
            "orchestrator_transition_triggered",
            run_id=run_id,
            stage=stage_key,
            done=done,
            total=total,
            threshold=threshold,
            early=(done < total),
        )
        _ = _settings  # silence unused if not needed; helper imports for future use
        await transition()

    async def on_s1_complete(
        self, run_id: str, video_id: str, pattern_summary: dict | None = None,
    ) -> None:
        from app.config import settings as _settings

        done = await self._r.incr(f"run:{run_id}:s1:done")
        config = await self._load_config(run_id)

        event_data: dict = {
            "video_id": video_id,
            "completed": done,
            "total": config.num_videos,
        }
        if pattern_summary:
            event_data.update(pattern_summary)

        await self._xadd_event(run_id, "s1_progress", event_data)

        await self._try_transition(
            run_id, "s2", done, config.num_videos,
            _settings.s1_completion_threshold,
            lambda: self._transition_s2(run_id),
        )

    async def on_s1_skipped(
        self, run_id: str, video_id: str, reason: str,
    ) -> None:
        """Mark one video as un-analyzable after retries exhausted.

        Bumps the same counter as a successful analysis so S2 can still
        trigger when the last video is processed. One bad input should
        never block the other 99.
        """
        done = await self._r.incr(f"run:{run_id}:s1:done")
        config = await self._load_config(run_id)

        await self._xadd_event(run_id, "s1_video_skipped", {
            "video_id": video_id,
            "reason": reason[:300],
            "completed": done,
            "total": config.num_videos,
        })
        logger.warning(
            "orchestrator_s1_video_skipped",
            run_id=run_id,
            video_id=video_id,
            reason=reason[:200],
        )

        from app.config import settings as _settings
        await self._try_transition(
            run_id, "s2", done, config.num_videos,
            _settings.s1_completion_threshold,
            lambda: self._transition_s2(run_id),
        )

    async def on_s2_complete(self, run_id: str, pattern_count: int = 0) -> None:
        await self._xadd_event(run_id, "s2_complete", {"pattern_count": pattern_count})
        await self._transition_s3(run_id)

    async def on_s3_complete(self, run_id: str) -> None:
        config = await self._load_config(run_id)
        raw = await self._r.get(f"scripts:candidates:{run_id}")
        script_ids: list[str] = []
        if raw:
            candidates = json.loads(raw)
            script_ids = [c["script_id"] for c in candidates]
        await self._xadd_event(run_id, "s3_complete", {
            "script_count": config.num_scripts,
            "script_ids": script_ids,
        })
        await self._transition_s4(run_id, config)

    async def on_s4_complete(
        self,
        run_id: str,
        persona_id: str,
        top_5: list[str] | None = None,
        persona_name: str | None = None,
        persona_description: str | None = None,
    ) -> None:
        done = await self._r.incr(f"run:{run_id}:s4:done")
        config = await self._load_config(run_id)

        # Checkpoint: persist progress so crash recovery can resume from here
        await self._r.write_checkpoint(run_id, "s4", done)

        event_data: dict = {
            "persona_id": persona_id,
            "persona_name": persona_name or persona_id,
            "top_5": top_5 or [],
            "completed": done,
            "total": config.num_personas,
        }
        if persona_description:
            event_data["persona_description"] = persona_description

        await self._xadd_event(run_id, "vote_cast", event_data)

        from app.config import settings as _settings
        await self._try_transition(
            run_id, "s5", done, config.num_personas,
            _settings.s4_completion_threshold,
            lambda: self._transition_s5(run_id),
        )

    async def recover(self, run_id: str) -> None:
        """Resume a crashed run from the last S4 checkpoint.

        Reads checkpoint:s4 to find how many personas completed before the
        crash, then re-dispatches only the remaining persona tasks.
        Called by the /api/pipeline/{run_id}/recover endpoint (or manually).
        """
        config = await self._load_config(run_id)
        s4_done = await self._r.read_checkpoint(run_id, "s4") or 0

        await self._r.set(f"run:{run_id}:status", "running")
        await self._xadd_event(run_id, "pipeline_recovered", {
            "run_id": run_id,
            "s4_checkpoint": s4_done,
            "remaining_personas": config.num_personas - s4_done,
        })

        from pathlib import Path

        from app.config import settings
        from app.runner.data_loader import load_personas_from_json
        from app.workers.tasks import s4_vote_task

        personas_path = Path(settings.personas_path)
        if personas_path.exists():
            personas = load_personas_from_json(personas_path, limit=config.num_personas)
            for i in range(s4_done, min(len(personas), config.num_personas)):
                s4_vote_task.delay(run_id, json.dumps(personas[i]))
        else:
            for i in range(s4_done, config.num_personas):
                s4_vote_task.delay(run_id, json.dumps({"persona_id": f"persona_{i}"}))

        logger.info(
            "orchestrator_recovered",
            run_id=run_id,
            s4_checkpoint=s4_done,
            remaining=config.num_personas - s4_done,
        )

    async def on_s5_complete(self, run_id: str) -> None:
        config = await self._load_config(run_id)
        raw = await self._r.get(f"top_scripts:{run_id}")
        rankings = S5Rankings.model_validate_json(raw)

        await self._xadd_event(run_id, "s5_complete", {
            "top_ids": [r.script_id for r in rankings.top_10],
            "top_n": config.top_n,
        })
        await self._transition_s6(run_id, rankings, config)

    async def on_s6_complete(self, run_id: str, script_id: str) -> None:
        done = await self._r.incr(f"run:{run_id}:s6:done")
        config = await self._load_config(run_id)

        await self._xadd_event(run_id, "s6_progress", {
            "script_id": script_id,
            "completed": done,
            "total": config.top_n,
        })

        if done >= config.top_n:
            await self._finalize(run_id, config)

    async def on_failure(
        self, run_id: str, stage: str, error: str, recoverable: bool = False
    ) -> None:
        await self._r.set(f"run:{run_id}:status", "failed")
        await self._r.set(f"run:{run_id}:stage", "FAILED")
        await self._xadd_event(run_id, "pipeline_error", {
            "stage": stage,
            "error": error,
            "recoverable": recoverable,
        })
        await self._set_run_ttl(run_id)
        logger.error("orchestrator_failure", run_id=run_id, stage=stage, error=error)

    # ------------------------------------------------------------------
    # Stage transitions
    # ------------------------------------------------------------------

    async def _transition_s2(self, run_id: str) -> None:
        await self._r.set(f"run:{run_id}:stage", "S2_REDUCE")
        await self._xadd_event(run_id, "stage_started", {"stage": "S2_REDUCE", "total_items": 1})
        from app.workers.tasks import s2_aggregate_task
        s2_aggregate_task.delay(run_id)

    async def _transition_s3(self, run_id: str) -> None:
        await self._r.set(f"run:{run_id}:stage", "S3_SEQUENTIAL")
        await self._xadd_event(
            run_id, "stage_started", {"stage": "S3_SEQUENTIAL", "total_items": 1}
        )
        from app.workers.tasks import s3_generate_task
        s3_generate_task.delay(run_id)

    async def _transition_s4(self, run_id: str, config: PipelineConfig) -> None:
        await self._r.set(f"run:{run_id}:stage", "S4_MAP")
        await self._xadd_event(run_id, "stage_started", {
            "stage": "S4_MAP",
            "total_items": config.num_personas,
        })

        from pathlib import Path

        from app.config import settings
        from app.runner.data_loader import load_personas_from_json
        from app.workers.tasks import s4_vote_task

        personas_path = Path(settings.personas_path)
        if personas_path.exists():
            personas = load_personas_from_json(personas_path, limit=config.num_personas)
            for persona in personas:
                s4_vote_task.delay(run_id, json.dumps(persona))
            remaining = config.num_personas - len(personas)
            for i in range(remaining):
                pid = f"persona_{len(personas) + i}"
                s4_vote_task.delay(run_id, json.dumps({"persona_id": pid}))
        else:
            for i in range(config.num_personas):
                s4_vote_task.delay(run_id, json.dumps({"persona_id": f"persona_{i}"}))

    async def _transition_s5(self, run_id: str) -> None:
        await self._r.set(f"run:{run_id}:stage", "S5_REDUCE")
        await self._xadd_event(run_id, "stage_started", {"stage": "S5_REDUCE", "total_items": 1})
        from app.workers.tasks import s5_rank_task
        s5_rank_task.delay(run_id)

    async def _transition_s6(
        self, run_id: str, rankings: S5Rankings, config: PipelineConfig
    ) -> None:
        top_scripts = rankings.top_10[:config.top_n]
        await self._r.set(f"run:{run_id}:stage", "S6_PERSONALIZE")
        await self._xadd_event(run_id, "stage_started", {
            "stage": "S6_PERSONALIZE",
            "total_items": len(top_scripts),
        })
        from app.workers.tasks import s6_personalize_task
        for ranked in top_scripts:
            s6_personalize_task.delay(run_id, ranked.script_id)

    async def _finalize(self, run_id: str, config: PipelineConfig) -> None:
        """Assemble S6Output, persist to Redis, update status, set TTLs."""
        raw_rankings = await self._r.get(f"top_scripts:{run_id}")
        rankings = S5Rankings.model_validate_json(raw_rankings)

        results: list[FinalResult] = []
        for ranked in rankings.top_10[:config.top_n]:
            raw = await self._r.get(f"result:s6:{run_id}:{ranked.script_id}")
            if raw is not None:
                results.append(FinalResult.model_validate_json(raw))

        output = S6Output(
            run_id=run_id,
            results=results,
            creator_profile=config.creator_profile,
            completed_at=datetime.now(UTC),
        )

        await self._r.set(f"results:final:{run_id}", output.model_dump_json())
        await self._r.set(f"run:{run_id}:status", "completed")
        await self._r.set(f"run:{run_id}:stage", "COMPLETED")

        await self._xadd_event(run_id, "pipeline_complete", {
            "run_id": run_id,
            "result_count": len(results),
        })

        await self._set_run_ttl(run_id)
        logger.info("orchestrator_complete", run_id=run_id, results=len(results))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _load_config(self, run_id: str) -> PipelineConfig:
        raw = await self._r.get(f"run:{run_id}:config")
        return PipelineConfig.model_validate_json(raw)

    async def _xadd_event(self, run_id: str, event_type: str, data: dict) -> None:
        event = {
            "event": event_type,
            "data": data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await self._r.xadd(f"sse:{run_id}", {"payload": json.dumps(event)})

    async def _set_run_ttl(self, run_id: str) -> None:
        """Apply 24h TTL to all per-run keys after terminal state."""
        static_keys = [
            f"run:{run_id}:stage",
            f"run:{run_id}:config",
            f"run:{run_id}:status",
            f"run:{run_id}:s1:done",
            f"run:{run_id}:s4:done",
            f"run:{run_id}:s6:done",
            f"pattern_library:{run_id}",
            f"scripts:candidates:{run_id}",
            f"top_scripts:{run_id}",
            f"results:final:{run_id}",
            f"sse:{run_id}",
        ]
        for key in static_keys:
            await self._r.expire(key, TTL_SECONDS)

        # Dynamic keys (result:s1, result:s4, result:s6, checkpoint)
        for pattern in [
            f"result:s1:{run_id}:*",
            f"result:s4:{run_id}:*",
            f"result:s6:{run_id}:*",
            f"checkpoint:{run_id}:*",
        ]:
            for key in await self._r.keys(pattern):
                await self._r.expire(key, TTL_SECONDS)
