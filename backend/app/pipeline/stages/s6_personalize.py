import json

import structlog

from app.models.errors import InvalidResponseError, StageError
from app.models.pipeline import CreatorProfile
from app.models.stages import CandidateScript, FinalResult, S6Response
from app.pipeline.prompts.s6_prompts import S6_PERSONALIZE_PROMPT
from app.providers.base import ReasoningProvider

logger = structlog.get_logger()


def _build_creator_context(profile: CreatorProfile) -> str:
    """Build optional Creator Context section from expanded fields."""
    lines = []
    if profile.niche:
        lines.append(f"Niche: {profile.niche}")
    if profile.audience_description:
        lines.append(f"Target audience: {profile.audience_description}")
    if profile.content_themes:
        lines.append(f"Content themes: {', '.join(profile.content_themes)}")
    if profile.example_hooks:
        lines.append(f"Hooks that worked before: {' | '.join(profile.example_hooks)}")
    if profile.recent_topics:
        lines.append(f"Recently covered (avoid repeating): {', '.join(profile.recent_topics)}")

    if not lines:
        return ""
    return "\n## Creator Context\n" + "\n".join(lines) + "\n"


async def s6_personalize(
    script: CandidateScript,
    profile: CreatorProfile,
    provider: ReasoningProvider,
) -> FinalResult:
    """Rewrite script in creator's voice + generate video prompt. Pure function."""
    creator_context = _build_creator_context(profile)
    niche_instruction = (
        f" Ground the content in the creator's niche ({profile.niche}) — "
        "use domain-specific references their audience expects."
        if profile.niche
        else ""
    )

    prompt = S6_PERSONALIZE_PROMPT.format(
        hook=script.hook,
        body=script.body,
        payoff=script.payoff,
        pattern_used=script.pattern_used,
        estimated_duration=script.estimated_duration,
        tone=profile.tone,
        vocabulary=", ".join(profile.vocabulary),
        catchphrases=", ".join(profile.catchphrases),
        topics_to_avoid=", ".join(profile.topics_to_avoid),
        creator_context=creator_context,
        niche_instruction=niche_instruction,
    )

    try:
        response = await provider.generate_text(prompt, schema=S6Response)
        data = json.loads(response)

        # LLM sometimes returns video_prompt as a nested object instead of string
        video_prompt = data["video_prompt"]
        if isinstance(video_prompt, dict):
            video_prompt = json.dumps(video_prompt)

        personalized_script = data["personalized_script"]
        if isinstance(personalized_script, dict):
            personalized_script = json.dumps(personalized_script)

        return FinalResult(
            script_id=script.script_id,
            original_script=script,
            personalized_script=personalized_script,
            video_prompt=video_prompt,
        )
    except json.JSONDecodeError as e:
        raise InvalidResponseError(
            f"S6 failed to parse response for {script.script_id}",
            provider=provider.name,
            raw_response=response,
            stage="S6",
        ) from e
    except (InvalidResponseError, StageError):
        raise
    except Exception as e:
        raise StageError(
            f"S6 failed for {script.script_id}: {e}",
            stage="S6",
        ) from e
