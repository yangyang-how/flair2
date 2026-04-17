import json

import structlog

from app.models.errors import InvalidResponseError, StageError
from app.models.stages import S1Pattern, VideoInput
from app.pipeline.prompts.s1_prompts import S1_ANALYZE_PROMPT
from app.providers.base import ReasoningProvider

logger = structlog.get_logger()


async def s1_analyze(video: VideoInput, provider: ReasoningProvider) -> S1Pattern:
    """Extract structural patterns from one video. Pure function."""
    prompt = S1_ANALYZE_PROMPT.format(
        video_id=video.video_id,
        duration=video.duration,
        description=video.description or "(no description)",
        transcript=video.transcript or "(no transcript)",
        engagement=json.dumps(video.engagement),
    )

    try:
        response = await provider.generate_text(
            prompt, schema=S1Pattern, max_tokens=2048, temperature=0.2
        )
        data = json.loads(response)
        # Ensure video_id matches input (LLM may hallucinate a different one)
        data["video_id"] = video.video_id
        return S1Pattern(**data)
    except json.JSONDecodeError as e:
        raise InvalidResponseError(
            f"S1 failed to parse LLM response for {video.video_id}",
            provider=provider.name,
            raw_response=response,
            stage="S1",
        ) from e
    except (InvalidResponseError, StageError):
        raise
    except Exception as e:
        raise StageError(
            f"S1 failed for {video.video_id}: {e}",
            stage="S1",
        ) from e
