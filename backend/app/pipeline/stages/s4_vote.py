import json

import structlog

from app.models.errors import InvalidResponseError, StageError
from app.models.performance import VideoPerformance
from app.models.stages import CandidateScript, PersonaVote
from app.pipeline.prompts.s4_prompts import S4_FEEDBACK_SECTION, S4_VOTE_PROMPT
from app.providers.base import ReasoningProvider

logger = structlog.get_logger()


def _build_scripts_section(scripts: list[CandidateScript]) -> str:
    lines = []
    for s in scripts:
        lines.append(
            f"### {s.script_id}\n"
            f"Pattern: {s.pattern_used}\n"
            f"Hook: {s.hook}\n"
            f"Body: {s.body}\n"
            f"Payoff: {s.payoff}\n"
            f"Duration: ~{s.estimated_duration}s\n"
        )
    return "\n".join(lines)


def _build_feedback_section(feedback: list[VideoPerformance] | None) -> str:
    if not feedback:
        return ""
    lines = []
    for vp in sorted(feedback, key=lambda x: x.views, reverse=True)[:5]:
        lines.append(
            f"- Rank {vp.committee_rank} predicted → Actual: {vp.views} views, {vp.likes} likes"
        )
    return S4_FEEDBACK_SECTION.format(feedback_data="\n".join(lines))


def _build_persona_section(persona_id: str, persona_data: dict | None) -> str:
    if not persona_data or "description" not in persona_data:
        return (
            f"Persona ID: {persona_id}\n"
            "You are a unique viewer with your own preferences, age, interests, "
            "and content consumption habits. Generate a brief description of who "
            "you are, then evaluate the scripts from that perspective."
        )
    parts = [f"Persona ID: {persona_id}"]
    if persona_data.get("name"):
        parts.append(f"Name: {persona_data['name']}")
    if persona_data.get("age"):
        parts.append(f"Age: {persona_data['age']}")
    if persona_data.get("location"):
        parts.append(f"Location: {persona_data['location']}")
    if persona_data.get("occupation"):
        parts.append(f"Occupation: {persona_data['occupation']}")
    if persona_data.get("interests"):
        parts.append(f"Interests: {', '.join(persona_data['interests'])}")
    if persona_data.get("platform_behavior"):
        parts.append(f"Platform behavior: {persona_data['platform_behavior']}")
    if persona_data.get("attention_style"):
        parts.append(f"Attention style: {persona_data['attention_style']}")
    parts.append(f"Profile: {persona_data['description']}")
    parts.append("Evaluate the scripts from this persona's perspective. Stay in character.")
    return "\n".join(parts)


async def s4_vote(
    scripts: list[CandidateScript],
    persona_id: str,
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
    persona_data: dict | None = None,
) -> PersonaVote:
    """One persona evaluates all scripts, picks top 5. Pure function."""
    prompt = S4_VOTE_PROMPT.format(
        persona_section=_build_persona_section(persona_id, persona_data),
        persona_id=persona_id,
        scripts_section=_build_scripts_section(scripts),
        feedback_section=_build_feedback_section(feedback),
    )

    try:
        response = await provider.generate_text(prompt, schema=PersonaVote, max_tokens=1024)
        data = json.loads(response)
        data["persona_id"] = persona_id
        return PersonaVote(**data)
    except json.JSONDecodeError as e:
        raise InvalidResponseError(
            f"S4 failed to parse vote from {persona_id}",
            provider=provider.name,
            raw_response=response,
            stage="S4",
        ) from e
    except (InvalidResponseError, StageError):
        raise
    except Exception as e:
        raise StageError(
            f"S4 failed for {persona_id}: {e}",
            stage="S4",
        ) from e
