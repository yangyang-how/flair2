import json

import pytest

from app.models.stages import CandidateScript, PatternEntry, S2PatternLibrary
from app.pipeline.stages.s3_generate import s3_generate


@pytest.fixture
def sample_library():
    return S2PatternLibrary(
        patterns=[
            PatternEntry(
                pattern_type="question + fast_slow_fast",
                frequency=25,
                examples=["v1"],
                avg_engagement=100000,
            ),
            PatternEntry(
                pattern_type="shock + escalating",
                frequency=15,
                examples=["v2"],
                avg_engagement=80000,
            ),
        ],
        total_videos_analyzed=100,
    )


@pytest.mark.asyncio
async def test_s3_generate_returns_scripts(sample_library, mock_provider):
    call_count = 0

    async def mock_gen(prompt, schema=None, max_tokens=None):
        nonlocal call_count
        call_count += 1
        return json.dumps(
            {
                "script_id": f"script_{call_count:03d}",
                "pattern_used": "question + fast_slow_fast",
                "hook": "Did you know most people waste their morning?",
                "body": "Here are 3 things you can do instead...",
                "payoff": "Start tomorrow. You won't regret it.",
                "estimated_duration": 25.0,
                "structural_notes": "Question hook with list structure",
            }
        )

    mock_provider.generate_text = mock_gen
    result = await s3_generate(sample_library, mock_provider, feedback=None, num_scripts=5)
    assert isinstance(result, list)
    assert all(isinstance(s, CandidateScript) for s in result)
    assert len(result) == 5


@pytest.mark.asyncio
async def test_s3_generate_assigns_unique_ids(sample_library, mock_provider):
    async def mock_gen(prompt, schema=None, max_tokens=None):
        return json.dumps(
            {
                "script_id": "will_be_overridden",
                "pattern_used": "question + fast_slow_fast",
                "hook": "hook",
                "body": "body",
                "payoff": "payoff",
                "estimated_duration": 20.0,
                "structural_notes": "notes",
            }
        )

    mock_provider.generate_text = mock_gen
    result = await s3_generate(sample_library, mock_provider, feedback=None, num_scripts=3)
    ids = [s.script_id for s in result]
    assert len(set(ids)) == len(ids), "Script IDs must be unique"
