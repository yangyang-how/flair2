import json

import pytest

from app.models.stages import CandidateScript, FinalResult
from app.pipeline.stages.s6_personalize import s6_personalize


@pytest.fixture
def sample_script():
    return CandidateScript(
        script_id="script_001",
        pattern_used="question + fast_slow_fast",
        hook="Did you know most people waste their morning?",
        body="Here are 3 things you can do instead...",
        payoff="Start tomorrow. You won't regret it.",
        estimated_duration=25.0,
        structural_notes="Question hook with list",
    )


@pytest.mark.asyncio
async def test_s6_returns_final_result(sample_script, sample_creator_profile, mock_provider):
    async def mock_gen(prompt, schema=None):
        return json.dumps({
            "personalized_script": "Yo what's up, so lowkey most people waste their mornings...",
            "video_prompt": "Fast-paced montage of morning routine clips with text overlays.",
        })

    mock_provider.generate_text = mock_gen
    result = await s6_personalize(sample_script, sample_creator_profile, mock_provider)
    assert isinstance(result, FinalResult)
    assert result.script_id == "script_001"
    assert result.personalized_script != ""
    assert result.video_prompt != ""
    assert result.original_script == sample_script


@pytest.mark.asyncio
async def test_s6_preserves_original_script(sample_script, sample_creator_profile, mock_provider):
    async def mock_gen(prompt, schema=None):
        return json.dumps({
            "personalized_script": "Rewritten version",
            "video_prompt": "Visual prompt",
        })

    mock_provider.generate_text = mock_gen
    result = await s6_personalize(sample_script, sample_creator_profile, mock_provider)
    assert result.original_script.hook == sample_script.hook
    assert result.original_script.body == sample_script.body
