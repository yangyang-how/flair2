import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import MagicMock

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


def _script_json(**kwargs) -> str:
    base = {
        "script_id": "x",
        "pattern_used": "question + fast_slow_fast",
        "hook": "h",
        "body": "b",
        "payoff": "p",
        "estimated_duration": 20.0,
        "structural_notes": "n",
    }
    base.update(kwargs)
    return json.dumps(base)


@pytest.mark.asyncio
async def test_s3_generate_returns_scripts(sample_library, mock_provider):
    call_count = 0

    async def mock_gen(prompt, schema=None, max_tokens=None, temperature=None):
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
    async def mock_gen(prompt, schema=None, max_tokens=None, temperature=None):
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


@pytest.mark.asyncio
async def test_s3_generate_runs_concurrently(sample_library):
    """All LLM calls are launched via asyncio.gather — peak in-flight > 1."""
    active = 0
    peak = [0]

    async def mock_gen(prompt, schema=None, max_tokens=None, temperature=None):
        nonlocal active
        active += 1
        peak[0] = max(peak[0], active)
        await asyncio.sleep(0)  # yield so other coroutines start
        active -= 1
        return _script_json()

    provider = MagicMock()
    provider.generate_text = mock_gen

    await s3_generate(sample_library, provider, feedback=None, num_scripts=5)
    assert peak[0] > 1, (
        f"Expected concurrent execution (peak > 1), got peak={peak[0]}. "
        "Concurrent generation should overlap LLM calls."
    )


@pytest.mark.asyncio
async def test_s3_generate_individual_failures_caught_not_propagated(sample_library):
    """_generate_one swallows individual exceptions — failure returns None, not a raised error.
    When generated < target the stage raises StageError (not the original exception).
    """
    from app.models.errors import StageError

    call_count = 0

    async def mock_gen(prompt, schema=None, max_tokens=None, temperature=None):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise ValueError("transient LLM error — must not propagate raw")
        return _script_json()

    provider = MagicMock()
    provider.generate_text = mock_gen

    # Individual exceptions are caught; if generated < target, StageError is raised.
    with pytest.raises(StageError, match="S3 generated only"):
        await s3_generate(sample_library, provider, feedback=None, num_scripts=4)

    # All 4 assignments were attempted — gather did not short-circuit on failure
    assert call_count == 4


@pytest.mark.asyncio
async def test_s3_generate_slot_factory_acquired_per_script(sample_library):
    """slot_factory is entered once per concurrent script generation call."""
    acquire_count = 0

    @asynccontextmanager
    async def counting_slot():
        nonlocal acquire_count
        acquire_count += 1
        yield

    provider = MagicMock()

    async def mock_gen(prompt, schema=None, max_tokens=None, temperature=None):
        return _script_json()

    provider.generate_text = mock_gen

    result = await s3_generate(
        sample_library, provider, feedback=None, num_scripts=4,
        slot_factory=counting_slot,
    )
    assert acquire_count == len(result), (
        f"slot_factory should be acquired once per script, "
        f"got {acquire_count} acquires for {len(result)} scripts"
    )
