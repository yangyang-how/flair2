import json
from pathlib import Path

import pytest

from app.models.stages import S1Pattern, VideoInput
from app.pipeline.stages.s1_analyze import s1_analyze

MOCK_S1_RESPONSE = json.dumps(
    {
        "video_id": "vid_001",
        "hook_type": "question",
        "pacing": "fast_slow_fast",
        "emotional_arc": "curiosity_to_challenge",
        "pattern_interrupts": ["list enumeration at 8s", "direct challenge at 25s"],
        "retention_mechanics": ["open loop: what's the third thing?", "dare at end"],
        "engagement_triggers": ["relatability", "practical value", "social currency"],
        "structure_notes": (
            "Opens with question hook, builds through numbered list, closes with dare."
        ),
    }
)


@pytest.fixture
def sample_video():
    fixture = Path(__file__).parent.parent / "fixtures" / "sample_video_input.json"
    data = json.loads(fixture.read_text())
    return VideoInput(**data)


@pytest.mark.asyncio
async def test_s1_analyze_returns_s1_pattern(sample_video, mock_provider):
    async def mock_gen(prompt, schema=None, max_tokens=None):
        return MOCK_S1_RESPONSE

    mock_provider.generate_text = mock_gen
    result = await s1_analyze(sample_video, mock_provider)
    assert isinstance(result, S1Pattern)
    assert result.video_id == "vid_001"
    assert result.hook_type == "question"


@pytest.mark.asyncio
async def test_s1_analyze_preserves_video_id(sample_video, mock_provider):
    async def mock_gen(prompt, schema=None, max_tokens=None):
        # Return a response with wrong video_id — stage should override
        data = json.loads(MOCK_S1_RESPONSE)
        data["video_id"] = "wrong_id"
        return json.dumps(data)

    mock_provider.generate_text = mock_gen
    result = await s1_analyze(sample_video, mock_provider)
    assert result.video_id == sample_video.video_id
