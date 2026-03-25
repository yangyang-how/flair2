# MVP Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A locally-running Python pipeline that analyzes 100 videos, generates 50 scripts, runs crowd-simulation voting, personalizes the top 10, and outputs scripts + video prompts — ready for video generation and posting.

**Architecture:** Pure async functions per stage, no Redis/Celery. Local runner calls stages sequentially. Pydantic models enforce typed contracts at every boundary. One LLM provider (Gemini) for MVP. See `design/architecture_v3.md` for full design.

**Tech Stack:** Python 3.11+, FastAPI (installed but not used in MVP), Pydantic 2, google-genai (Gemini), pytest, ruff, structlog.

**Spec:** `design/spec_v3.md` (v3.2)
**Architecture:** `design/architecture_v3.md` (v3.0)
**Knowledge Base:** `design/research/` (psychology, hooks, formats, algorithms, personas)

---

## File Map

All paths relative to `backend/`.

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `pyproject.toml` | Dependencies, project config, ruff/pytest config |
| Create | `app/__init__.py` | Package marker |
| Create | `app/config.py` | pydantic-settings, env-based config |
| Create | `app/models/__init__.py` | Package marker |
| Create | `app/models/pipeline.py` | PipelineConfig, CreatorProfile, PipelineRun, enums |
| Create | `app/models/stages.py` | VideoInput, S1Pattern, S2PatternLibrary, CandidateScript, PersonaVote, S5Rankings, FinalResult, S6Output |
| Create | `app/models/performance.py` | VideoPerformance |
| Create | `app/models/errors.py` | PipelineError, ProviderError, StageError, InfraError hierarchy |
| Create | `app/providers/__init__.py` | Package marker |
| Create | `app/providers/base.py` | ReasoningProvider, VideoProvider protocols |
| Create | `app/providers/registry.py` | Provider name → instance lookup |
| Create | `app/providers/gemini.py` | Gemini implementation of ReasoningProvider |
| Create | `app/pipeline/__init__.py` | Package marker |
| Create | `app/pipeline/stages/__init__.py` | Package marker |
| Create | `app/pipeline/stages/s1_analyze.py` | `s1_analyze(video, provider) -> S1Pattern` |
| Create | `app/pipeline/stages/s2_aggregate.py` | `s2_aggregate(patterns) -> S2PatternLibrary` |
| Create | `app/pipeline/stages/s3_generate.py` | `s3_generate(library, provider, feedback) -> list[CandidateScript]` |
| Create | `app/pipeline/stages/s4_vote.py` | `s4_vote(scripts, persona_id, provider, feedback) -> PersonaVote` |
| Create | `app/pipeline/stages/s5_rank.py` | `s5_rank(votes) -> S5Rankings` |
| Create | `app/pipeline/stages/s6_personalize.py` | `s6_personalize(script, profile, provider) -> FinalResult` |
| Create | `app/pipeline/prompts/__init__.py` | Package marker |
| Create | `app/pipeline/prompts/s1_prompts.py` | S1 structural pattern extraction prompt template |
| Create | `app/pipeline/prompts/s3_prompts.py` | S3 script generation prompt template |
| Create | `app/pipeline/prompts/s4_prompts.py` | S4 persona evaluation prompt template |
| Create | `app/pipeline/prompts/s6_prompts.py` | S6 style injection + video prompt template |
| Create | `app/runner/__init__.py` | Package marker |
| Create | `app/runner/local_runner.py` | `run_pipeline()` — sequential execution of all stages |
| Create | `app/runner/cli.py` | CLI entry point — parse args, load data, run pipeline, save output |
| Create | `app/runner/data_loader.py` | Load dataset (CSV/Parquet), select top 100 by engagement |
| Create | `tests/__init__.py` | Package marker |
| Create | `tests/conftest.py` | MockReasoningProvider, shared fixtures |
| Create | `tests/fixtures/sample_video_input.json` | Sample VideoInput for testing |
| Create | `tests/fixtures/sample_creator_profile.json` | Sample CreatorProfile for testing |
| Create | `tests/unit/__init__.py` | Package marker |
| Create | `tests/unit/test_models.py` | Model validation tests |
| Create | `tests/unit/test_s1_analyze.py` | S1 unit test |
| Create | `tests/unit/test_s2_aggregate.py` | S2 unit test |
| Create | `tests/unit/test_s3_generate.py` | S3 unit test |
| Create | `tests/unit/test_s4_vote.py` | S4 unit test |
| Create | `tests/unit/test_s5_rank.py` | S5 unit test |
| Create | `tests/unit/test_s6_personalize.py` | S6 unit test |
| Create | `tests/unit/test_local_runner.py` | Full pipeline local mode test |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/conftest.py`

- [ ] **Step 1: Create backend directory and pyproject.toml**

```toml
# backend/pyproject.toml
[project]
name = "flair2"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.1",
    "google-genai>=0.4",
    "httpx>=0.27",
    "structlog>=24.1",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "ruff>=0.3",
]

[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create app package and config**

```python
# backend/app/__init__.py
```

```python
# backend/app/config.py
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "flair2"
    debug: bool = False
    environment: str = "dev"

    # LLM API Keys
    gemini_api_key: str = ""
    kimi_api_key: str = ""
    openai_api_key: str = ""

    # Pipeline Defaults
    s1_video_count: int = 100
    s3_script_count: int = 50
    s4_persona_count: int = 100
    s6_top_n: int = 10

    model_config = {"env_file": ".env", "env_prefix": "FLAIR2_"}


settings = Settings()
```

- [ ] **Step 3: Create test scaffolding**

```python
# backend/tests/__init__.py
```

```python
# backend/tests/conftest.py
import pytest


@pytest.fixture
def sample_creator_profile():
    from app.models.pipeline import CreatorProfile
    return CreatorProfile(
        tone="casual and energetic",
        vocabulary=["vibe", "insane", "lowkey", "no cap"],
        catchphrases=["let's gooo", "wait for it"],
        topics_to_avoid=["politics", "religion"],
    )
```

- [ ] **Step 4: Install dependencies and verify**

Run: `cd backend && pip install -e ".[dev]"`
Expected: Successful installation, no errors.

- [ ] **Step 5: Verify ruff and pytest work**

Run: `cd backend && ruff check . && pytest`
Expected: ruff passes (no files to check yet), pytest collects 0 tests.

- [ ] **Step 6: Commit**

```bash
git add backend/pyproject.toml backend/app/__init__.py backend/app/config.py backend/tests/__init__.py backend/tests/conftest.py
git commit -m "chore: scaffold backend project with dependencies and config"
```

---

## Task 2: Pydantic Data Models

**Files:**
- Create: `backend/app/models/__init__.py`
- Create: `backend/app/models/pipeline.py`
- Create: `backend/app/models/stages.py`
- Create: `backend/app/models/performance.py`
- Create: `backend/app/models/errors.py`
- Test: `backend/tests/unit/test_models.py`

- [ ] **Step 1: Write failing test for models**

```python
# backend/tests/unit/__init__.py
```

```python
# backend/tests/unit/test_models.py
from datetime import datetime

from app.models.pipeline import CreatorProfile, PipelineConfig, PipelineStatus
from app.models.stages import (
    CandidateScript,
    FinalResult,
    PatternEntry,
    PersonaVote,
    RankedScript,
    S1Pattern,
    S2PatternLibrary,
    S5Rankings,
    S6Output,
    VideoInput,
)
from app.models.performance import VideoPerformance
from app.models.errors import (
    InfraError,
    InvalidResponseError,
    PipelineError,
    ProviderError,
    RateLimitError,
    StageError,
)


def test_creator_profile_valid():
    p = CreatorProfile(
        tone="casual",
        vocabulary=["vibe", "insane"],
        catchphrases=["let's go"],
        topics_to_avoid=["politics"],
    )
    assert p.tone == "casual"
    assert len(p.vocabulary) == 2


def test_pipeline_config_valid():
    c = PipelineConfig(
        run_id="test-run-1",
        session_id="session-1",
        reasoning_model="gemini",
        video_model=None,
        creator_profile=CreatorProfile(
            tone="edgy", vocabulary=[], catchphrases=[], topics_to_avoid=[]
        ),
    )
    assert c.reasoning_model == "gemini"
    assert c.video_model is None


def test_video_input_valid():
    v = VideoInput(
        video_id="vid_001",
        transcript="Hey what's up, today we're going to...",
        description="How to go viral #fyp",
        duration=15.0,
        engagement={"views": 1000000, "likes": 50000},
    )
    assert v.duration == 15.0


def test_s1_pattern_valid():
    p = S1Pattern(
        video_id="vid_001",
        hook_type="question",
        pacing="fast_slow_fast",
        emotional_arc="curiosity_gap",
        pattern_interrupts=["visual cut at 3s"],
        retention_mechanics=["open loop"],
        engagement_triggers=["relatability"],
        structure_notes="Opens with a direct question, slow reveal, payoff at end",
    )
    assert p.hook_type == "question"


def test_s2_pattern_library():
    lib = S2PatternLibrary(
        patterns=[
            PatternEntry(
                pattern_type="question_hook",
                frequency=25,
                examples=["vid_001", "vid_015"],
                avg_engagement=85000.0,
            ),
        ],
        total_videos_analyzed=100,
    )
    assert lib.total_videos_analyzed == 100
    assert lib.patterns[0].frequency == 25


def test_candidate_script():
    s = CandidateScript(
        script_id="script_001",
        pattern_used="question_hook + fast_slow_fast",
        hook="Have you ever wondered why some videos get millions of views?",
        body="The secret is in the first 3 seconds...",
        payoff="Try this on your next video and watch what happens.",
        estimated_duration=30.0,
        structural_notes="Question hook, curiosity gap, practical payoff",
    )
    assert s.estimated_duration == 30.0


def test_persona_vote():
    v = PersonaVote(
        persona_id="persona_0",
        persona_description="18-year-old college student, watches comedy and lifestyle content",
        top_5_script_ids=["script_001", "script_015", "script_030", "script_042", "script_007"],
        reasoning="Script 001 had the strongest hook...",
    )
    assert len(v.top_5_script_ids) == 5


def test_s5_rankings():
    r = S5Rankings(
        top_10=[
            RankedScript(script_id="script_001", vote_count=45, score=0.92, rank=1),
            RankedScript(script_id="script_015", vote_count=38, score=0.85, rank=2),
        ],
        total_votes_cast=100,
    )
    assert r.top_10[0].rank == 1


def test_video_performance():
    vp = VideoPerformance(
        run_id="run-1",
        script_id="script_001",
        platform="tiktok",
        post_url="https://tiktok.com/@user/video/123",
        posted_at=datetime.utcnow(),
        views=50000,
        likes=3000,
        comments=150,
        shares=500,
        watch_time_avg=12.5,
        completion_rate=65.0,
        committee_rank=1,
        script_pattern="question_hook",
    )
    assert vp.platform == "tiktok"


def test_error_hierarchy():
    base = PipelineError("something broke", run_id="run-1", stage="S1", attempt=2)
    assert base.run_id == "run-1"
    assert base.stage == "S1"
    assert isinstance(base, Exception)

    provider = ProviderError("API down", provider="gemini", status_code=500, run_id="run-1")
    assert isinstance(provider, PipelineError)
    assert provider.provider == "gemini"

    rate = RateLimitError("too fast", provider="gemini", retry_after=30.0)
    assert isinstance(rate, ProviderError)

    invalid = InvalidResponseError("bad json", provider="gemini", raw_response="{broken")
    assert isinstance(invalid, ProviderError)

    stage = StageError("logic error", run_id="run-1", stage="S3")
    assert isinstance(stage, PipelineError)

    infra = InfraError("connection lost", service="redis")
    assert isinstance(infra, PipelineError)
    assert infra.service == "redis"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.models'`

- [ ] **Step 3: Write all model files**

Create all four model files exactly as specified in `design/architecture_v3.md` Sections 4.1, 4.2, 4.3, 4.4.

Files:
- `backend/app/models/__init__.py` (empty)
- `backend/app/models/pipeline.py` (CreatorProfile, PipelineConfig, PipelineRun, enums)
- `backend/app/models/stages.py` (VideoInput, S1Pattern, S2PatternLibrary, CandidateScript, PersonaVote, RankedScript, S5Rankings, FinalResult, S6Output)
- `backend/app/models/performance.py` (VideoPerformance)
- `backend/app/models/errors.py` (PipelineError hierarchy)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_models.py -v`
Expected: All tests PASS.

- [ ] **Step 5: Run linter**

Run: `cd backend && ruff check .`
Expected: No errors.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/ backend/tests/unit/
git commit -m "feat: add Pydantic data models for all pipeline stages"
```

---

## Task 3: Provider Interface + Gemini Implementation

**Files:**
- Create: `backend/app/providers/__init__.py`
- Create: `backend/app/providers/base.py`
- Create: `backend/app/providers/registry.py`
- Create: `backend/app/providers/gemini.py`
- Test: `backend/tests/unit/test_provider_registry.py`
- Modify: `backend/tests/conftest.py` (add MockReasoningProvider)

- [ ] **Step 1: Write failing test for provider registry**

```python
# backend/tests/unit/test_provider_registry.py
from app.providers.base import ReasoningProvider
from app.providers.registry import get_reasoning_provider, list_providers


def test_list_providers_includes_gemini():
    providers = list_providers()
    assert "gemini" in providers["reasoning"]


def test_get_gemini_provider():
    provider = get_reasoning_provider("gemini")
    assert provider.name == "gemini"
    assert hasattr(provider, "generate_text")
    assert hasattr(provider, "analyze_content")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_provider_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.providers'`

- [ ] **Step 3: Create provider base protocols**

```python
# backend/app/providers/__init__.py
```

```python
# backend/app/providers/base.py
from typing import Protocol

from pydantic import BaseModel


class ReasoningProvider(Protocol):
    name: str

    async def generate_text(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> str: ...

    async def analyze_content(
        self,
        content: str,
        prompt: str,
    ) -> str: ...


class VideoJobStatus(BaseModel):
    job_id: str
    status: str
    video_url: str | None = None
    error: str | None = None


class VideoProvider(Protocol):
    name: str

    async def generate_video(
        self,
        prompt: str,
        duration: int = 6,
    ) -> bytes: ...

    async def check_status(
        self,
        job_id: str,
    ) -> VideoJobStatus: ...
```

- [ ] **Step 4: Create Gemini provider**

```python
# backend/app/providers/gemini.py
import json
import re

import structlog
from google import genai
from pydantic import BaseModel

from app.config import settings
from app.models.errors import InvalidResponseError, ProviderError, RateLimitError

logger = structlog.get_logger()

# Retry backoff seconds (from V1 pattern)
BACKOFF_SECS = [1, 2, 4]
MAX_RETRIES = 3


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response, stripping markdown fences."""
    # Try to find ```json ... ``` blocks
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # Try raw JSON
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text
    return text


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.0-flash"):
        self._api_key = api_key or settings.gemini_api_key
        self._model = model
        self._client = genai.Client(api_key=self._api_key)

    async def generate_text(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> str:
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                )
                text = response.text
                if schema:
                    json_str = _extract_json(text)
                    # Validate it parses
                    try:
                        json.loads(json_str)
                    except json.JSONDecodeError as e:
                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                "invalid_json_response",
                                attempt=attempt,
                                error=str(e),
                            )
                            continue
                        raise InvalidResponseError(
                            f"Failed to parse JSON after {MAX_RETRIES} attempts",
                            provider=self.name,
                            raw_response=text,
                        )
                    return json_str
                return text
            except Exception as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    if attempt < MAX_RETRIES - 1:
                        import asyncio
                        await asyncio.sleep(BACKOFF_SECS[attempt])
                        continue
                    raise RateLimitError(
                        f"Rate limited after {MAX_RETRIES} retries",
                        provider=self.name,
                        retry_after=BACKOFF_SECS[-1] * 2,
                    )
                raise ProviderError(
                    str(e),
                    provider=self.name,
                    status_code=getattr(e, "status_code", None),
                )
        raise ProviderError("Unexpected retry exhaustion", provider=self.name)

    async def analyze_content(self, content: str, prompt: str) -> str:
        full_prompt = f"{prompt}\n\nContent to analyze:\n{content}"
        return await self.generate_text(full_prompt)
```

- [ ] **Step 5: Create registry**

```python
# backend/app/providers/registry.py
from app.providers.gemini import GeminiProvider

_reasoning_providers: dict[str, type] = {
    "gemini": GeminiProvider,
}
_video_providers: dict[str, type] = {}


def register_reasoning(name: str, cls: type) -> None:
    _reasoning_providers[name] = cls


def register_video(name: str, cls: type) -> None:
    _video_providers[name] = cls


def get_reasoning_provider(name: str, **kwargs):
    if name not in _reasoning_providers:
        raise ValueError(f"Unknown reasoning provider: {name}. Available: {list(_reasoning_providers)}")
    return _reasoning_providers[name](**kwargs)


def get_video_provider(name: str, **kwargs):
    if name not in _video_providers:
        raise ValueError(f"Unknown video provider: {name}. Available: {list(_video_providers)}")
    return _video_providers[name](**kwargs)


def list_providers() -> dict:
    return {
        "reasoning": list(_reasoning_providers.keys()),
        "video": list(_video_providers.keys()),
    }
```

- [ ] **Step 6: Add MockReasoningProvider to conftest**

Append to `backend/tests/conftest.py`:

```python
import json


class MockReasoningProvider:
    """Mock provider returning canned JSON for each stage."""
    name = "mock"

    def __init__(self):
        self.call_log: list[str] = []

    async def generate_text(self, prompt: str, schema=None) -> str:
        self.call_log.append(prompt[:50])
        if schema:
            return json.dumps(schema.model_json_schema().get("examples", [{}])[0] if hasattr(schema, "model_json_schema") else {})
        return "Mock generated text response."

    async def analyze_content(self, content: str, prompt: str) -> str:
        self.call_log.append(f"analyze: {prompt[:50]}")
        return await self.generate_text(prompt)


@pytest.fixture
def mock_provider():
    return MockReasoningProvider()
```

- [ ] **Step 7: Run tests**

Run: `cd backend && pytest tests/unit/test_provider_registry.py -v`
Expected: All PASS.

- [ ] **Step 8: Run linter**

Run: `cd backend && ruff check .`
Expected: No errors.

- [ ] **Step 9: Commit**

```bash
git add backend/app/providers/ backend/tests/
git commit -m "feat: add provider interface, Gemini implementation, and registry"
```

---

## Task 4: S1 Analyze + S2 Aggregate (MapReduce Cycle 1)

**Files:**
- Create: `backend/app/pipeline/__init__.py`
- Create: `backend/app/pipeline/stages/__init__.py`
- Create: `backend/app/pipeline/stages/s1_analyze.py`
- Create: `backend/app/pipeline/stages/s2_aggregate.py`
- Create: `backend/app/pipeline/prompts/__init__.py`
- Create: `backend/app/pipeline/prompts/s1_prompts.py`
- Test: `backend/tests/unit/test_s1_analyze.py`
- Test: `backend/tests/unit/test_s2_aggregate.py`
- Create: `backend/tests/fixtures/sample_video_input.json`

- [ ] **Step 1: Create test fixture**

```json
// backend/tests/fixtures/sample_video_input.json
{
    "video_id": "vid_001",
    "transcript": "Have you ever noticed that the most successful people wake up before 5am? Here's what they do differently. First, they don't check their phone. Instead, they spend 10 minutes in silence. Second, they write down three things they're grateful for. And third - this is the one nobody talks about - they do the hardest task first. Try this for one week. I dare you.",
    "description": "Morning routine secrets of successful people #productivity #morning #habits",
    "duration": 28.0,
    "engagement": {"views": 2500000, "likes": 180000, "comments": 4500, "shares": 25000}
}
```

- [ ] **Step 2: Write failing test for S1**

```python
# backend/tests/unit/test_s1_analyze.py
import json
from pathlib import Path

import pytest

from app.models.stages import S1Pattern, VideoInput
from app.pipeline.stages.s1_analyze import s1_analyze


@pytest.fixture
def sample_video():
    fixture = Path(__file__).parent.parent / "fixtures" / "sample_video_input.json"
    data = json.loads(fixture.read_text())
    return VideoInput(**data)


@pytest.mark.asyncio
async def test_s1_analyze_returns_s1_pattern(sample_video, mock_provider):
    # Mock provider to return a valid S1Pattern JSON
    import json as json_mod
    mock_provider.generate_text = lambda prompt, schema=None: _mock_s1_response()
    result = await s1_analyze(sample_video, mock_provider)
    assert isinstance(result, S1Pattern)
    assert result.video_id == "vid_001"
    assert result.hook_type in ["question", "shock", "story", "direct_address"]


async def _mock_s1_response():
    return json.dumps({
        "video_id": "vid_001",
        "hook_type": "question",
        "pacing": "fast_slow_fast",
        "emotional_arc": "curiosity_to_challenge",
        "pattern_interrupts": ["list enumeration at 8s", "direct challenge at 25s"],
        "retention_mechanics": ["open loop: what's the third thing?", "dare at end"],
        "engagement_triggers": ["relatability", "practical value", "social currency"],
        "structure_notes": "Opens with question hook, builds through a numbered list, closes with a direct challenge/dare."
    })


@pytest.mark.asyncio
async def test_s1_analyze_includes_video_id(sample_video, mock_provider):
    mock_provider.generate_text = lambda prompt, schema=None: _mock_s1_response()
    result = await s1_analyze(sample_video, mock_provider)
    assert result.video_id == sample_video.video_id
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_s1_analyze.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipeline'`

- [ ] **Step 4: Create S1 prompt template**

```python
# backend/app/pipeline/prompts/__init__.py
```

```python
# backend/app/pipeline/prompts/s1_prompts.py

S1_ANALYZE_PROMPT = """You are a short-form video content analyst. Analyze this video and extract its STRUCTURAL patterns — not surface trends.

## Video Information
- Video ID: {video_id}
- Duration: {duration}s
- Description: {description}
- Transcript: {transcript}
- Engagement: {engagement}

## What to Extract (structural only)

1. **hook_type**: How does the video open? One of: "question", "shock", "story", "direct_address"
2. **pacing**: What is the rhythm? e.g., "fast_slow_fast", "escalating", "steady", "staccato"
3. **emotional_arc**: What emotional journey? e.g., "curiosity_gap", "negative_to_positive", "tension_release", "surprise_reveal"
4. **pattern_interrupts**: List of techniques used to maintain attention (visual cuts, topic shifts, tonal changes)
5. **retention_mechanics**: What keeps viewers watching? (open loops, payoff delays, numbered lists, dares/challenges)
6. **engagement_triggers**: What drives likes/shares/comments? (relatability, practical value, social currency, controversy, humor)
7. **structure_notes**: Free-form notes on the overall structure and why it works

## What NOT to Extract
- Do NOT extract specific sounds, dances, memes, challenges, hashtags, or trends
- Focus on the STRUCTURE that makes this video work, not the specific CONTENT

## Output Format
Respond with ONLY a JSON object matching this schema:
{{
    "video_id": "{video_id}",
    "hook_type": "...",
    "pacing": "...",
    "emotional_arc": "...",
    "pattern_interrupts": ["...", "..."],
    "retention_mechanics": ["...", "..."],
    "engagement_triggers": ["...", "..."],
    "structure_notes": "..."
}}
"""
```

- [ ] **Step 5: Implement S1 analyze**

```python
# backend/app/pipeline/__init__.py
```

```python
# backend/app/pipeline/stages/__init__.py
```

```python
# backend/app/pipeline/stages/s1_analyze.py
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
        response = await provider.generate_text(prompt, schema=S1Pattern)
        data = json.loads(response)
        # Ensure video_id matches input
        data["video_id"] = video.video_id
        return S1Pattern(**data)
    except json.JSONDecodeError as e:
        raise InvalidResponseError(
            f"S1 failed to parse LLM response for {video.video_id}",
            provider=provider.name,
            raw_response=str(e),
            stage="S1",
        )
    except Exception as e:
        if isinstance(e, (InvalidResponseError, StageError)):
            raise
        raise StageError(
            f"S1 failed for {video.video_id}: {e}",
            stage="S1",
        )
```

- [ ] **Step 6: Run S1 tests**

Run: `cd backend && pytest tests/unit/test_s1_analyze.py -v`
Expected: All PASS.

- [ ] **Step 7: Write failing test for S2**

```python
# backend/tests/unit/test_s2_aggregate.py
from app.models.stages import S1Pattern, S2PatternLibrary
from app.pipeline.stages.s2_aggregate import s2_aggregate


def _make_pattern(video_id: str, hook_type: str, pacing: str) -> S1Pattern:
    return S1Pattern(
        video_id=video_id,
        hook_type=hook_type,
        pacing=pacing,
        emotional_arc="curiosity_gap",
        pattern_interrupts=["cut"],
        retention_mechanics=["open loop"],
        engagement_triggers=["relatability"],
        structure_notes="test pattern",
    )


def test_s2_aggregate_groups_by_pattern():
    patterns = [
        _make_pattern("v1", "question", "fast_slow_fast"),
        _make_pattern("v2", "question", "fast_slow_fast"),
        _make_pattern("v3", "shock", "escalating"),
        _make_pattern("v4", "question", "fast_slow_fast"),
    ]
    result = s2_aggregate(patterns)
    assert isinstance(result, S2PatternLibrary)
    assert result.total_videos_analyzed == 4
    # Most frequent pattern should be first
    assert result.patterns[0].frequency >= result.patterns[1].frequency


def test_s2_aggregate_empty_input():
    result = s2_aggregate([])
    assert result.total_videos_analyzed == 0
    assert len(result.patterns) == 0


def test_s2_aggregate_single_pattern():
    patterns = [_make_pattern("v1", "story", "steady")]
    result = s2_aggregate(patterns)
    assert len(result.patterns) == 1
    assert result.patterns[0].frequency == 1
```

- [ ] **Step 8: Implement S2 aggregate**

```python
# backend/app/pipeline/stages/s2_aggregate.py
from collections import Counter, defaultdict

from app.models.stages import PatternEntry, S1Pattern, S2PatternLibrary


def s2_aggregate(patterns: list[S1Pattern]) -> S2PatternLibrary:
    """Merge N patterns into a ranked library. No LLM — pure algorithmic."""
    if not patterns:
        return S2PatternLibrary(patterns=[], total_videos_analyzed=0)

    # Group by hook_type + pacing combination
    pattern_key = lambda p: f"{p.hook_type} + {p.pacing}"
    groups: dict[str, list[S1Pattern]] = defaultdict(list)
    for p in patterns:
        groups[pattern_key(p)].append(p)

    # Build entries sorted by frequency
    entries = []
    for key, group in groups.items():
        avg_eng = 0.0
        for p in group:
            eng = p.model_dump().get("engagement", {})
            if isinstance(eng, dict):
                avg_eng += eng.get("views", 0)
        avg_eng = avg_eng / len(group) if group else 0

        entries.append(
            PatternEntry(
                pattern_type=key,
                frequency=len(group),
                examples=[p.video_id for p in group[:5]],
                avg_engagement=avg_eng,
            )
        )

    entries.sort(key=lambda e: e.frequency, reverse=True)

    return S2PatternLibrary(
        patterns=entries,
        total_videos_analyzed=len(patterns),
    )
```

- [ ] **Step 9: Run S2 tests**

Run: `cd backend && pytest tests/unit/test_s2_aggregate.py -v`
Expected: All PASS.

- [ ] **Step 10: Run all tests + linter**

Run: `cd backend && ruff check . && pytest -v`
Expected: All pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/pipeline/ backend/tests/
git commit -m "feat: add S1 analyze + S2 aggregate (MapReduce Cycle 1)"
```

---

## Task 5: S3 Generate + S4 Vote + S5 Rank (MapReduce Cycle 2)

**Files:**
- Create: `backend/app/pipeline/stages/s3_generate.py`
- Create: `backend/app/pipeline/stages/s4_vote.py`
- Create: `backend/app/pipeline/stages/s5_rank.py`
- Create: `backend/app/pipeline/prompts/s3_prompts.py`
- Create: `backend/app/pipeline/prompts/s4_prompts.py`
- Test: `backend/tests/unit/test_s3_generate.py`
- Test: `backend/tests/unit/test_s4_vote.py`
- Test: `backend/tests/unit/test_s5_rank.py`

- [ ] **Step 1: Write failing test for S3**

```python
# backend/tests/unit/test_s3_generate.py
import json

import pytest

from app.models.stages import CandidateScript, PatternEntry, S2PatternLibrary
from app.pipeline.stages.s3_generate import s3_generate


@pytest.fixture
def sample_library():
    return S2PatternLibrary(
        patterns=[
            PatternEntry(pattern_type="question + fast_slow_fast", frequency=25, examples=["v1"], avg_engagement=100000),
            PatternEntry(pattern_type="shock + escalating", frequency=15, examples=["v2"], avg_engagement=80000),
        ],
        total_videos_analyzed=100,
    )


@pytest.mark.asyncio
async def test_s3_generate_returns_scripts(sample_library, mock_provider):
    # Mock to return a valid CandidateScript JSON
    call_count = 0

    async def mock_generate(prompt, schema=None):
        nonlocal call_count
        call_count += 1
        return json.dumps({
            "script_id": f"script_{call_count:03d}",
            "pattern_used": "question + fast_slow_fast",
            "hook": "Did you know most people waste their morning?",
            "body": "Here are 3 things you can do instead...",
            "payoff": "Start tomorrow. You won't regret it.",
            "estimated_duration": 25.0,
            "structural_notes": "Question hook with list structure",
        })

    mock_provider.generate_text = mock_generate
    result = await s3_generate(sample_library, mock_provider, feedback=None)
    assert isinstance(result, list)
    assert all(isinstance(s, CandidateScript) for s in result)
    assert len(result) > 0
```

- [ ] **Step 2: Create S3 prompt and implementation**

Create `backend/app/pipeline/prompts/s3_prompts.py` with a prompt template that:
- Takes the pattern library as context
- Generates one script per call using the specified pattern
- Includes optional feedback data (past performance) when available
- Outputs JSON matching CandidateScript schema

Create `backend/app/pipeline/stages/s3_generate.py`:
- Iterates through top patterns from the library
- Generates scripts proportional to pattern frequency (more frequent = more scripts)
- Total target: `settings.s3_script_count` (default 50)
- Sequential — deliberate bottleneck for Amdahl's Law
- Returns `list[CandidateScript]`

- [ ] **Step 3: Run S3 tests**

Run: `cd backend && pytest tests/unit/test_s3_generate.py -v`
Expected: PASS.

- [ ] **Step 4: Write failing test for S4**

```python
# backend/tests/unit/test_s4_vote.py
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
    async def mock_generate(prompt, schema=None):
        return json.dumps({
            "persona_id": "persona_0",
            "persona_description": "18-year-old student who watches comedy",
            "top_5_script_ids": ["script_000", "script_003", "script_007", "script_001", "script_005"],
            "reasoning": "Script 000 had the strongest hook...",
        })

    mock_provider.generate_text = mock_generate
    result = await s4_vote(sample_scripts, "persona_0", mock_provider, feedback=None)
    assert isinstance(result, PersonaVote)
    assert result.persona_id == "persona_0"
    assert len(result.top_5_script_ids) == 5
```

- [ ] **Step 5: Create S4 prompt and implementation**

Create `backend/app/pipeline/prompts/s4_prompts.py` with a prompt that:
- Generates a diverse persona description based on persona_id
- Presents all candidate scripts for evaluation
- Asks the persona to pick top 5 with reasoning
- Includes optional feedback for calibration

Create `backend/app/pipeline/stages/s4_vote.py`:
- Takes scripts, persona_id, provider, optional feedback
- Returns PersonaVote

- [ ] **Step 6: Run S4 tests**

Run: `cd backend && pytest tests/unit/test_s4_vote.py -v`
Expected: PASS.

- [ ] **Step 7: Write failing test for S5**

```python
# backend/tests/unit/test_s5_rank.py
from app.models.stages import PersonaVote, RankedScript, S5Rankings
from app.pipeline.stages.s5_rank import s5_rank


def test_s5_rank_aggregates_votes():
    votes = [
        PersonaVote(
            persona_id=f"persona_{i}",
            persona_description="test",
            top_5_script_ids=["script_001", "script_003", "script_005", "script_007", "script_009"],
            reasoning="test",
        )
        for i in range(60)
    ] + [
        PersonaVote(
            persona_id=f"persona_{i}",
            persona_description="test",
            top_5_script_ids=["script_002", "script_004", "script_006", "script_008", "script_001"],
            reasoning="test",
        )
        for i in range(40)
    ]
    result = s5_rank(votes)
    assert isinstance(result, S5Rankings)
    assert len(result.top_10) == 10
    assert result.top_10[0].rank == 1
    assert result.total_votes_cast == 100
    # script_001 appears in all 100 votes, should be ranked highest
    assert result.top_10[0].script_id == "script_001"


def test_s5_rank_scores_descending():
    votes = [
        PersonaVote(
            persona_id=f"p_{i}",
            persona_description="test",
            top_5_script_ids=["s1", "s2", "s3", "s4", "s5"],
            reasoning="test",
        )
        for i in range(10)
    ]
    result = s5_rank(votes)
    scores = [r.score for r in result.top_10]
    assert scores == sorted(scores, reverse=True)
```

- [ ] **Step 8: Implement S5 rank**

```python
# backend/app/pipeline/stages/s5_rank.py
from collections import Counter

from app.config import settings
from app.models.stages import PersonaVote, RankedScript, S5Rankings


def s5_rank(votes: list[PersonaVote]) -> S5Rankings:
    """Aggregate votes into ranked top 10. No LLM — pure algorithmic.

    Scoring: Each vote position gets a weighted score.
    1st pick = 5pts, 2nd = 4pts, 3rd = 3pts, 4th = 2pts, 5th = 1pt.
    Mirrors TikTok's engagement weighting (rewatch > completion > share > comment > like).
    """
    score_weights = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1}
    scores: Counter[str] = Counter()
    vote_counts: Counter[str] = Counter()

    for vote in votes:
        for position, script_id in enumerate(vote.top_5_script_ids):
            scores[script_id] += score_weights.get(position, 1)
            vote_counts[script_id] += 1

    top_n = settings.s6_top_n
    top_scripts = scores.most_common(top_n)

    ranked = [
        RankedScript(
            script_id=script_id,
            vote_count=vote_counts[script_id],
            score=float(score),
            rank=rank + 1,
        )
        for rank, (script_id, score) in enumerate(top_scripts)
    ]

    return S5Rankings(
        top_10=ranked,
        total_votes_cast=len(votes),
    )
```

- [ ] **Step 9: Run S5 tests**

Run: `cd backend && pytest tests/unit/test_s5_rank.py -v`
Expected: PASS.

- [ ] **Step 10: Run all tests + linter**

Run: `cd backend && ruff check . && pytest -v`
Expected: All pass.

- [ ] **Step 11: Commit**

```bash
git add backend/app/pipeline/stages/ backend/app/pipeline/prompts/ backend/tests/unit/
git commit -m "feat: add S3 generate + S4 vote + S5 rank (MapReduce Cycle 2)"
```

---

## Task 6: S6 Personalize

**Files:**
- Create: `backend/app/pipeline/stages/s6_personalize.py`
- Create: `backend/app/pipeline/prompts/s6_prompts.py`
- Test: `backend/tests/unit/test_s6_personalize.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/unit/test_s6_personalize.py
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
async def test_s6_personalize_returns_final_result(
    sample_script, sample_creator_profile, mock_provider
):
    async def mock_generate(prompt, schema=None):
        return json.dumps({
            "personalized_script": "Yo what's up, so lowkey most people are wasting their mornings...",
            "video_prompt": "A fast-paced montage of morning routine clips with text overlays...",
        })

    mock_provider.generate_text = mock_generate
    result = await s6_personalize(sample_script, sample_creator_profile, mock_provider)
    assert isinstance(result, FinalResult)
    assert result.script_id == "script_001"
    assert result.personalized_script != ""
    assert result.video_prompt != ""
    assert result.original_script == sample_script
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_s6_personalize.py -v`
Expected: FAIL.

- [ ] **Step 3: Create S6 prompt and implementation**

Create `backend/app/pipeline/prompts/s6_prompts.py` with prompt template for style injection + video prompt generation.

Create `backend/app/pipeline/stages/s6_personalize.py`:
- Takes CandidateScript, CreatorProfile, provider
- Returns FinalResult with personalized_script, video_prompt, and original metadata

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/unit/test_s6_personalize.py -v`
Expected: PASS.

- [ ] **Step 5: Run all tests + linter**

Run: `cd backend && ruff check . && pytest -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app/pipeline/stages/s6_personalize.py backend/app/pipeline/prompts/s6_prompts.py backend/tests/unit/test_s6_personalize.py
git commit -m "feat: add S6 personalize — style injection + video prompt generation"
```

---

## Task 7: Local Runner + CLI

**Files:**
- Create: `backend/app/runner/__init__.py`
- Create: `backend/app/runner/local_runner.py`
- Create: `backend/app/runner/data_loader.py`
- Create: `backend/app/runner/cli.py`
- Test: `backend/tests/unit/test_local_runner.py`
- Create: `backend/tests/fixtures/sample_creator_profile.json`

- [ ] **Step 1: Create creator profile fixture**

```json
// backend/tests/fixtures/sample_creator_profile.json
{
    "tone": "casual and energetic",
    "vocabulary": ["vibe", "insane", "lowkey", "no cap", "fire"],
    "catchphrases": ["let's gooo", "wait for it", "trust me on this"],
    "topics_to_avoid": ["politics", "religion", "negativity"]
}
```

- [ ] **Step 2: Write failing test for local runner**

```python
# backend/tests/unit/test_local_runner.py
import json

import pytest

from app.models.pipeline import CreatorProfile, PipelineConfig
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
            transcript=f"Test transcript for video {i}",
            description=f"Test description {i} #test",
            duration=15.0 + i,
            engagement={"views": 1000 * (i + 1), "likes": 100 * (i + 1)},
        )
        for i in range(3)
    ]


@pytest.mark.asyncio
async def test_local_runner_produces_output(mini_config, mini_videos, mock_provider):
    # Override settings for small test
    result = await run_pipeline(
        config=mini_config,
        videos=mini_videos,
        provider=mock_provider,
        feedback=None,
        num_scripts=5,
        num_personas=3,
        top_n=2,
    )
    assert isinstance(result, S6Output)
    assert result.run_id == "test-run"
    assert len(result.results) <= 2
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_local_runner.py -v`
Expected: FAIL.

- [ ] **Step 4: Implement local runner**

```python
# backend/app/runner/__init__.py
```

```python
# backend/app/runner/local_runner.py
from datetime import datetime, timezone

import structlog

from app.config import settings
from app.models.pipeline import PipelineConfig
from app.models.performance import VideoPerformance
from app.models.stages import S6Output, VideoInput
from app.pipeline.stages.s1_analyze import s1_analyze
from app.pipeline.stages.s2_aggregate import s2_aggregate
from app.pipeline.stages.s3_generate import s3_generate
from app.pipeline.stages.s4_vote import s4_vote
from app.pipeline.stages.s5_rank import s5_rank
from app.pipeline.stages.s6_personalize import s6_personalize
from app.providers.base import ReasoningProvider

logger = structlog.get_logger()


async def run_pipeline(
    config: PipelineConfig,
    videos: list[VideoInput],
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
    num_scripts: int | None = None,
    num_personas: int | None = None,
    top_n: int | None = None,
) -> S6Output:
    """Run full pipeline locally. No Redis, no Celery.
    Same stage functions as distributed mode.

    Optional params override settings for testing with smaller numbers.
    """
    _num_scripts = num_scripts or settings.s3_script_count
    _num_personas = num_personas or settings.s4_persona_count
    _top_n = top_n or settings.s6_top_n

    logger.info("pipeline_start", run_id=config.run_id, videos=len(videos))

    # S1: Analyze all videos
    logger.info("s1_start", count=len(videos))
    patterns = []
    for i, video in enumerate(videos):
        pattern = await s1_analyze(video, provider)
        patterns.append(pattern)
        logger.info("s1_progress", completed=i + 1, total=len(videos))
    logger.info("s1_complete", patterns=len(patterns))

    # S2: Aggregate
    logger.info("s2_start")
    library = s2_aggregate(patterns)
    logger.info("s2_complete", pattern_types=len(library.patterns))

    # S3: Generate scripts
    logger.info("s3_start", target=_num_scripts)
    scripts = await s3_generate(library, provider, feedback)
    logger.info("s3_complete", scripts=len(scripts))

    # S4: Vote
    logger.info("s4_start", personas=_num_personas)
    votes = []
    for i in range(_num_personas):
        vote = await s4_vote(scripts, f"persona_{i}", provider, feedback)
        votes.append(vote)
        logger.info("s4_progress", completed=i + 1, total=_num_personas)
    logger.info("s4_complete", votes=len(votes))

    # S5: Rank
    logger.info("s5_start")
    rankings = s5_rank(votes)
    logger.info("s5_complete", top_10=[r.script_id for r in rankings.top_10])

    # S6: Personalize top N
    logger.info("s6_start", count=min(_top_n, len(rankings.top_10)))
    results = []
    for ranked in rankings.top_10[:_top_n]:
        # Find the full script object
        script = next((s for s in scripts if s.script_id == ranked.script_id), None)
        if script is None:
            logger.warning("script_not_found", script_id=ranked.script_id)
            continue
        result = await s6_personalize(script, config.creator_profile, provider)
        result.rank = ranked.rank
        result.vote_score = ranked.score
        results.append(result)
    logger.info("s6_complete", results=len(results))

    output = S6Output(
        run_id=config.run_id,
        results=results,
        creator_profile=config.creator_profile,
        completed_at=datetime.now(timezone.utc),
    )

    logger.info("pipeline_complete", run_id=config.run_id, results=len(results))
    return output
```

- [ ] **Step 5: Implement data loader**

```python
# backend/app/runner/data_loader.py
import json
from pathlib import Path

import structlog

from app.models.stages import VideoInput

logger = structlog.get_logger()


def load_videos_from_json(path: Path, limit: int = 100) -> list[VideoInput]:
    """Load videos from a JSON file (array of video objects)."""
    data = json.loads(path.read_text())
    if isinstance(data, list):
        videos = [VideoInput(**v) for v in data[:limit]]
    else:
        raise ValueError(f"Expected JSON array, got {type(data)}")
    logger.info("loaded_videos", count=len(videos), source=str(path))
    return videos


def load_videos_from_parquet(path: Path, limit: int = 100) -> list[VideoInput]:
    """Load videos from a Parquet file (e.g., HuggingFace dataset)."""
    try:
        import polars as pl
    except ImportError:
        raise ImportError("polars is required for Parquet loading: pip install polars")

    df = pl.read_parquet(path)
    # Sort by engagement (views) descending, take top N
    if "play_count" in df.columns:
        df = df.sort("play_count", descending=True).head(limit)
    elif "views" in df.columns:
        df = df.sort("views", descending=True).head(limit)

    videos = []
    for row in df.iter_rows(named=True):
        video = VideoInput(
            video_id=str(row.get("id", row.get("video_id", ""))),
            transcript=row.get("transcript"),
            description=row.get("desc", row.get("description")),
            duration=float(row.get("duration", 0)),
            engagement={
                "views": row.get("play_count", row.get("views", 0)),
                "likes": row.get("digg_count", row.get("likes", 0)),
                "comments": row.get("comment_count", row.get("comments", 0)),
                "shares": row.get("share_count", row.get("shares", 0)),
            },
        )
        videos.append(video)

    logger.info("loaded_videos", count=len(videos), source=str(path))
    return videos
```

- [ ] **Step 6: Implement CLI entry point**

```python
# backend/app/runner/cli.py
import argparse
import asyncio
import json
import uuid
from pathlib import Path

import structlog

from app.config import settings
from app.models.pipeline import CreatorProfile, PipelineConfig
from app.providers.registry import get_reasoning_provider
from app.runner.data_loader import load_videos_from_json, load_videos_from_parquet
from app.runner.local_runner import run_pipeline

logger = structlog.get_logger()


def main():
    parser = argparse.ArgumentParser(description="Flair2 MVP Pipeline — Local Mode")
    parser.add_argument("--data", required=True, help="Path to video dataset (JSON or Parquet)")
    parser.add_argument("--profile", required=True, help="Path to creator_profile.json")
    parser.add_argument("--provider", default="gemini", help="Reasoning provider (default: gemini)")
    parser.add_argument("--output", default="output.json", help="Output file path")
    parser.add_argument("--limit", type=int, default=100, help="Number of videos to analyze")
    args = parser.parse_args()

    # Load data
    data_path = Path(args.data)
    if data_path.suffix == ".parquet":
        videos = load_videos_from_parquet(data_path, limit=args.limit)
    else:
        videos = load_videos_from_json(data_path, limit=args.limit)

    # Load creator profile
    profile_data = json.loads(Path(args.profile).read_text())
    profile = CreatorProfile(**profile_data)

    # Build config
    config = PipelineConfig(
        run_id=str(uuid.uuid4()),
        session_id="local",
        reasoning_model=args.provider,
        video_model=None,
        creator_profile=profile,
    )

    # Get provider
    provider = get_reasoning_provider(args.provider)

    # Run pipeline
    logger.info("cli_start", run_id=config.run_id, provider=args.provider, videos=len(videos))
    output = asyncio.run(run_pipeline(config, videos, provider))

    # Save output
    output_path = Path(args.output)
    output_path.write_text(output.model_dump_json(indent=2))
    logger.info("cli_complete", output=str(output_path), results=len(output.results))
    print(f"\nPipeline complete! {len(output.results)} results saved to {output_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: Run local runner test**

Run: `cd backend && pytest tests/unit/test_local_runner.py -v`
Expected: PASS.

- [ ] **Step 8: Run full test suite + linter**

Run: `cd backend && ruff check . && pytest -v`
Expected: All pass.

- [ ] **Step 9: Commit**

```bash
git add backend/app/runner/ backend/tests/
git commit -m "feat: add local runner, data loader, and CLI entry point"
```

---

## Task 8: Integration Test — Full Pipeline End-to-End

**Files:**
- Test: `backend/tests/unit/test_local_runner.py` (extend with full E2E)

- [ ] **Step 1: Extend the mock provider with realistic canned responses**

Update `MockReasoningProvider` in `conftest.py` so it returns structurally valid JSON for each stage based on prompt content. The mock should detect which stage is calling based on keywords in the prompt ("analyze", "generate script", "evaluate", "personalize").

- [ ] **Step 2: Run full pipeline test with 3 videos, 5 scripts, 3 personas, top 2**

Run: `cd backend && pytest tests/unit/test_local_runner.py -v`
Expected: PASS — full pipeline produces S6Output with results.

- [ ] **Step 3: Run complete test suite + linter**

Run: `cd backend && ruff check . && pytest -v --tb=short`
Expected: All tests pass. No lint errors.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/
git commit -m "test: add full pipeline integration test with mock provider"
```

---

## Summary

| Task | What | Commit Message |
|------|------|---------------|
| 1 | Project scaffolding | `chore: scaffold backend project with dependencies and config` |
| 2 | Pydantic models | `feat: add Pydantic data models for all pipeline stages` |
| 3 | Provider interface + Gemini | `feat: add provider interface, Gemini implementation, and registry` |
| 4 | S1 + S2 (MapReduce 1) | `feat: add S1 analyze + S2 aggregate (MapReduce Cycle 1)` |
| 5 | S3 + S4 + S5 (MapReduce 2) | `feat: add S3 generate + S4 vote + S5 rank (MapReduce Cycle 2)` |
| 6 | S6 Personalize | `feat: add S6 personalize — style injection + video prompt generation` |
| 7 | Local Runner + CLI | `feat: add local runner, data loader, and CLI entry point` |
| 8 | Integration test | `test: add full pipeline integration test with mock provider` |

**After completing all 8 tasks**, you can run the MVP pipeline:

```bash
cd backend
python -m app.runner.cli \
  --data ../data/sample_videos.json \
  --profile ../data/creator_profile.json \
  --provider gemini \
  --output results.json
```

**Next plans:**
- Plan 2: Distributed Infrastructure (API, Celery, Redis, orchestrator, AWS)
- Plan 3: Frontend (Astro, React islands, SSE)
