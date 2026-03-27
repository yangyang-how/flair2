import json

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


@pytest.mark.asyncio
async def test_s4_vote_returns_persona_vote(sample_scripts, mock_provider):
    async def mock_gen(prompt, schema=None):
        return json.dumps({
            "persona_id": "persona_0",
            "persona_description": "18-year-old student who watches comedy",
            "top_5_script_ids": [
                "script_000", "script_003", "script_007", "script_001", "script_005",
            ],
            "reasoning": "Script 000 had the strongest hook.",
        })

    mock_provider.generate_text = mock_gen
    result = await s4_vote(sample_scripts, "persona_0", mock_provider, feedback=None)
    assert isinstance(result, PersonaVote)
    assert result.persona_id == "persona_0"
    assert len(result.top_5_script_ids) == 5
