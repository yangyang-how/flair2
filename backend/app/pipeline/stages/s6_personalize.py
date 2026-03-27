import json

import structlog

from app.models.errors import InvalidResponseError, StageError
from app.models.pipeline import CreatorProfile
from app.models.stages import CandidateScript, FinalResult, S6Response
from app.pipeline.prompts.s6_prompts import S6_PERSONALIZE_PROMPT
from app.providers.base import ReasoningProvider

logger = structlog.get_logger()


async def s6_personalize(
    script: CandidateScript,
    profile: CreatorProfile,
    provider: ReasoningProvider,
) -> FinalResult:
    """Rewrite script in creator's voice + generate video prompt. Pure function."""
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
    )

    try:
        response = await provider.generate_text(prompt, schema=S6Response)
        data = json.loads(response)
        return FinalResult(
            script_id=script.script_id,
            original_script=script,
            personalized_script=data["personalized_script"],
            video_prompt=data["video_prompt"],
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
