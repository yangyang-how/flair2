import json
import uuid

import structlog

from app.config import settings
from app.models.errors import StageError
from app.models.performance import VideoPerformance
from app.models.stages import CandidateScript, S2PatternLibrary
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


async def s3_generate(
    library: S2PatternLibrary,
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
    num_scripts: int | None = None,
) -> list[CandidateScript]:
    """Generate candidate scripts. Sequential — deliberate bottleneck."""
    target = num_scripts or settings.s3_script_count
    feedback_section = _build_feedback_section(feedback)
    library_summary = _pattern_library_summary(library)

    # Distribute scripts across patterns proportional to frequency
    total_freq = sum(p.frequency for p in library.patterns) or 1
    scripts: list[CandidateScript] = []

    for pattern in library.patterns:
        count = max(1, round(target * pattern.frequency / total_freq))
        for _ in range(count):
            if len(scripts) >= target:
                break

            prompt = S3_GENERATE_PROMPT.format(
                pattern_type=pattern.pattern_type,
                pattern_library_summary=library_summary,
                feedback_section=feedback_section,
            )

            try:
                response = await provider.generate_text(prompt, schema=CandidateScript)
                data = json.loads(response)
                data["script_id"] = str(uuid.uuid4())[:8]
                scripts.append(CandidateScript(**data))
                logger.info("s3_script_generated", count=len(scripts), target=target)
            except Exception as e:
                logger.warning("s3_script_failed", error=str(e), pattern=pattern.pattern_type)
                continue

        if len(scripts) >= target:
            break

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
