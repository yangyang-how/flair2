import json

import pytest

from app.models.pipeline import PipelineConfig
from app.models.stages import S6Output, VideoInput
from app.runner.local_runner import run_pipeline


@pytest.fixture
def mini_config(sample_creator_profile):
    return PipelineConfig(
        run_id="test-run",
        session_id="test-session",
        reasoning_model="mock",
        video_model=None,
        creator_profile=sample_creator_profile,
    )


@pytest.fixture
def mini_videos():
    """3 videos instead of 100 for fast testing."""
    return [
        VideoInput(
            video_id=f"vid_{i:03d}",
            transcript=f"Test transcript for video {i}. This is a sample video about topic {i}.",
            description=f"Test description {i} #test #video",
            duration=15.0 + i,
            engagement={"views": 1000 * (i + 1), "likes": 100 * (i + 1)},
        )
        for i in range(3)
    ]


@pytest.fixture
def smart_mock_provider():
    """Mock that returns stage-appropriate canned responses."""

    class SmartMock:
        name = "mock"
        _script_count = 0

        async def generate_text(self, prompt, schema=None, max_tokens=None):
            prompt_lower = prompt.lower()
            if "content analyst" in prompt_lower or "what to extract" in prompt_lower:
                return json.dumps(
                    {
                        "video_id": "placeholder",
                        "hook_type": "question",
                        "pacing": "fast_slow_fast",
                        "emotional_arc": "curiosity_gap",
                        "pattern_interrupts": ["cut at 5s"],
                        "retention_mechanics": ["open loop"],
                        "engagement_triggers": ["relatability"],
                        "structure_notes": "Standard question hook structure",
                    }
                )
            elif "scriptwriter" in prompt_lower:
                self._script_count += 1
                return json.dumps(
                    {
                        "script_id": f"s_{self._script_count}",
                        "pattern_used": "question + fast_slow_fast",
                        "hook": f"Hook {self._script_count}: Did you know?",
                        "body": f"Body {self._script_count}: Here's the thing...",
                        "payoff": f"Payoff {self._script_count}: Try it!",
                        "estimated_duration": 25.0,
                        "structural_notes": "Question hook pattern",
                    }
                )
            elif "style adapter" in prompt_lower:
                return json.dumps(
                    {
                        "personalized_script": "Yo what's up, let's gooo — did you know...",
                        "video_prompt": "Fast cuts, text overlays, energetic music",
                    }
                )
            elif "persona" in prompt_lower:
                import re

                ids = re.findall(r"### ([\w-]+)", prompt)
                top5 = (ids[:5] if len(ids) >= 5 else ids + ids[:5])[:5]
                return json.dumps(
                    {
                        "persona_id": "placeholder",
                        "persona_description": "A 22-year-old who watches lifestyle content",
                        "top_5_script_ids": top5,
                        "reasoning": "These hooks were most engaging",
                    }
                )
            return json.dumps({"result": "mock response"})

        async def analyze_content(self, content, prompt):
            return await self.generate_text(prompt)

    return SmartMock()


@pytest.mark.asyncio
async def test_local_runner_full_pipeline(mini_config, mini_videos, smart_mock_provider):
    result = await run_pipeline(
        config=mini_config,
        videos=mini_videos,
        provider=smart_mock_provider,
        feedback=None,
        num_scripts=5,
        num_personas=3,
        top_n=2,
    )
    assert isinstance(result, S6Output)
    assert result.run_id == "test-run"
    assert len(result.results) == 2
    assert result.results[0].personalized_script != ""
    assert result.results[0].video_prompt != ""
    assert result.completed_at is not None
