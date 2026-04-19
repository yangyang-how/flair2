import json
from unittest.mock import MagicMock

import pytest

from app.models.stages import CandidateScript, PersonaVote
from app.pipeline.stages.s4_vote import s4_vote


@pytest.fixture
def sample_scripts():
    return [
        CandidateScript(
            script_id=f"script_{i:03d}",
            pattern_used="question + fast_slow_fast",
            hook=f"Hook number {i}",
            body=f"Body of script {i}",
            payoff=f"Payoff {i}",
            estimated_duration=25.0,
            structural_notes="test",
        )
        for i in range(10)
    ]


def _vote_response(persona_id: str = "persona_0") -> str:
    return json.dumps(
        {
            "persona_id": persona_id,
            "persona_description": "test persona",
            "top_5_script_ids": [f"script_{i:03d}" for i in range(5)],
            "reasoning": "test reasoning",
        }
    )


@pytest.mark.asyncio
async def test_s4_vote_returns_persona_vote(sample_scripts, mock_provider):
    async def mock_gen(prompt, schema=None, max_tokens=None, temperature=None):
        return json.dumps(
            {
                "persona_id": "persona_0",
                "persona_description": "18-year-old student who watches comedy",
                "top_5_script_ids": [
                    "script_000",
                    "script_003",
                    "script_007",
                    "script_001",
                    "script_005",
                ],
                "reasoning": "Script 000 had the strongest hook.",
            }
        )

    mock_provider.generate_text = mock_gen
    result = await s4_vote(sample_scripts, "persona_0", mock_provider, feedback=None)
    assert isinstance(result, PersonaVote)
    assert result.persona_id == "persona_0"
    assert len(result.top_5_script_ids) == 5


@pytest.mark.asyncio
async def test_s4_vote_injects_predefined_persona_into_prompt(sample_scripts):
    """When persona_data is provided, real profile fields appear in the LLM prompt."""
    captured: list[str] = []

    async def mock_gen(prompt, schema=None, max_tokens=None, temperature=None):
        captured.append(prompt)
        return _vote_response("persona_5")

    provider = MagicMock()
    provider.generate_text = mock_gen

    persona_data = {
        "name": "Mia Chen",
        "age": 24,
        "location": "Toronto",
        "occupation": "UX Designer",
        "interests": ["travel", "minimalism"],
        "platform_behavior": "saves videos for later",
        "attention_style": "skips if no hook in 2s",
        "description": "Mia is a design-conscious creator who values aesthetic.",
    }

    result = await s4_vote(
        sample_scripts, "persona_5", provider,
        feedback=None, persona_data=persona_data,
    )

    assert len(captured) == 1
    prompt = captured[0]
    assert "Mia Chen" in prompt, "Predefined name must appear in prompt"
    assert "UX Designer" in prompt, "Predefined occupation must appear in prompt"
    assert "Toronto" in prompt, "Predefined location must appear in prompt"
    assert isinstance(result, PersonaVote)


@pytest.mark.asyncio
async def test_s4_vote_fallback_when_no_persona_data(sample_scripts):
    """When persona_data=None, prompt asks LLM to invent a persona (no real fields)."""
    captured: list[str] = []

    async def mock_gen(prompt, schema=None, max_tokens=None, temperature=None):
        captured.append(prompt)
        return _vote_response("persona_1")

    provider = MagicMock()
    provider.generate_text = mock_gen

    await s4_vote(sample_scripts, "persona_1", provider, feedback=None, persona_data=None)

    prompt = captured[0]
    assert "persona_1" in prompt
    # Predefined fields must NOT appear when no persona_data supplied
    assert "UX Designer" not in prompt
    assert "Mia Chen" not in prompt
