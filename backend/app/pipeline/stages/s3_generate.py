import asyncio
import json
import uuid
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager, nullcontext

import structlog

from app.config import settings
from app.models.errors import StageError
from app.models.performance import VideoPerformance
from app.models.pipeline import CreatorProfile
from app.models.stages import CandidateScript, PatternEntry, S2PatternLibrary
from app.pipeline.prompts.s3_prompts import S3_FEEDBACK_SECTION, S3_GENERATE_PROMPT
from app.providers.base import ReasoningProvider

logger = structlog.get_logger()


def _build_feedback_section(feedback: list[VideoPerformance] | None) -> str:
    if not feedback:
        return ""
    lines = []
    for vp in sorted(feedback, key=lambda x: x.views, reverse=True)[:10]:
        lines.append(
            f"- Pattern: {vp.script_pattern}, Views: {vp.views}, "
            f"Likes: {vp.likes}, Completion: {vp.completion_rate}%"
        )
    return S3_FEEDBACK_SECTION.format(feedback_data="\n".join(lines))


def _pattern_library_summary(library: S2PatternLibrary) -> str:
    lines = []
    for p in library.patterns[:10]:
        lines.append(f"- {p.pattern_type} (seen {p.frequency} times)")
    return "\n".join(lines)


def _build_creator_context(profile: CreatorProfile | None) -> str:
    """Inject creator niche/themes so generated scripts are on-topic.

    Without this, S3 produces generic viral scripts whose topic reflects
    the analyzed video dataset (random TikTok content). S6 can then only
    adjust voice — not subject matter. Anchoring S3 to the creator's
    niche fixes the "Kitchen Confident got a productivity script" bug.
    """
    if not profile:
        return ""
    lines = []
    if profile.niche:
        lines.append(f"Niche: {profile.niche}")
    if profile.audience_description:
        lines.append(f"Target audience: {profile.audience_description}")
    if profile.content_themes:
        lines.append(f"Content themes: {', '.join(profile.content_themes)}")
    if profile.example_hooks:
        lines.append(f"Example hooks that worked: {' | '.join(profile.example_hooks[:3])}")
    if profile.recent_topics:
        lines.append(f"Recently covered (avoid repeating): {', '.join(profile.recent_topics)}")
    if not lines:
        return ""
    return "\n## Creator Context\n" + "\n".join(lines) + "\n"


def _niche_instruction(profile: CreatorProfile | None) -> str:
    if not profile or not profile.niche:
        return ""
    return (
        f"\n- **CRITICAL**: Ground the script in the creator's niche ({profile.niche}). "
        "The hook, body, and payoff must all be on-topic for this niche. "
        "Use the structural pattern to shape HOW the story is told, not WHAT the story is about."
    )


def _assign_patterns(library: S2PatternLibrary, target: int) -> list[PatternEntry]:
    total_freq = sum(p.frequency for p in library.patterns) or 1
    assignments: list[PatternEntry] = []
    for pattern in library.patterns:
        count = max(1, round(target * pattern.frequency / total_freq))
        for _ in range(count):
            if len(assignments) >= target:
                break
            assignments.append(pattern)
        if len(assignments) >= target:
            break
    return assignments


async def s3_generate(
    library: S2PatternLibrary,
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
    num_scripts: int | None = None,
    slot_factory: Callable[[], AbstractAsyncContextManager[None]] | None = None,
    creator_profile: CreatorProfile | None = None,
) -> list[CandidateScript]:
    """Generate candidate scripts concurrently, one LLM call per script."""
    target = num_scripts or settings.s3_script_count
    feedback_section = _build_feedback_section(feedback)
    library_summary = _pattern_library_summary(library)
    creator_context = _build_creator_context(creator_profile)
    niche_instruction = _niche_instruction(creator_profile)
    assignments = _assign_patterns(library, target)

    async def _generate_one(pattern: PatternEntry) -> CandidateScript | None:
        prompt = S3_GENERATE_PROMPT.format(
            pattern_type=pattern.pattern_type,
            pattern_library_summary=library_summary,
            feedback_section=feedback_section,
            creator_context=creator_context,
            niche_instruction=niche_instruction,
        )
        slot = slot_factory() if slot_factory is not None else nullcontext()
        async with slot:
            try:
                response = await provider.generate_text(
                    prompt, schema=CandidateScript, max_tokens=2048, temperature=0.9
                )
                data = json.loads(response)
                data["script_id"] = str(uuid.uuid4())[:8]
                return CandidateScript(**data)
            except Exception as e:
                logger.warning("s3_script_failed", error=str(e), pattern=pattern.pattern_type)
                return None

    results = await asyncio.gather(*[_generate_one(p) for p in assignments])
    scripts = [r for r in results if r is not None]
    logger.info("s3_generation_complete", generated=len(scripts), target=target)

    if not scripts:
        raise StageError("S3 generated zero scripts", stage="S3")

    if len(scripts) < target:
        logger.error(
            "s3_insufficient_scripts",
            generated=len(scripts),
            target=target,
        )
        raise StageError(
            f"S3 generated only {len(scripts)}/{target} scripts",
            stage="S3",
        )

    return scripts[:target]
