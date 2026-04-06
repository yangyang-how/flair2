# KimiProvider + Usage Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Gemini with Kimi as the default reasoning provider, add per-run usage tracking with visual progress.

**Architecture:** New `KimiProvider` using OpenAI SDK with Kimi Code endpoint. Extract shared `_extract_json` to utils. Add `UsageTracker` that accumulates per-stage stats and logs progress. Wire into registry and runner. Zero stage code changes.

**Tech Stack:** `openai>=1.0` (OpenAI SDK), `httpx>=0.27` (already in deps), `structlog` (already in deps)

**Issue:** #60

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/app/providers/utils.py` | Shared `_extract_json` + JSON parsing helpers |
| Create | `backend/app/providers/kimi.py` | KimiProvider — ReasoningProvider via OpenAI SDK |
| Create | `backend/app/providers/usage.py` | UsageTracker — per-stage request/token/latency stats |
| Create | `backend/tests/unit/test_kimi_provider.py` | KimiProvider unit tests |
| Create | `backend/tests/unit/test_usage_tracker.py` | UsageTracker unit tests |
| Modify | `backend/app/providers/gemini.py` | Remove `_extract_json`, import from utils |
| Modify | `backend/app/providers/registry.py` | Register `"kimi"` provider |
| Modify | `backend/app/runner/cli.py` | Default `--provider kimi`, add usage summary |
| Modify | `backend/app/runner/local_runner.py` | Integrate UsageTracker, pass stage names |
| Modify | `backend/pyproject.toml` | Add `openai>=1.0` dependency |
| Modify | `backend/tests/unit/test_provider_registry.py` | Add kimi registration test |

---

### Task 1: Extract shared `_extract_json` to utils

**Files:**
- Create: `backend/app/providers/utils.py`
- Modify: `backend/app/providers/gemini.py`

- [ ] **Step 1: Create `utils.py` with `_extract_json`**

```python
# backend/app/providers/utils.py
"""Shared provider utilities."""
import re


def extract_json(text: str) -> str:
    """Extract JSON from LLM response, stripping markdown fences."""
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    text = text.strip()
    if text.startswith("{") or text.startswith("["):
        return text
    return text
```

- [ ] **Step 2: Update `gemini.py` to import from utils**

Replace the local `_extract_json` function and its `import re` with:

```python
from app.providers.utils import extract_json
```

Replace all calls from `_extract_json(text)` to `extract_json(text)`.

- [ ] **Step 3: Run tests to confirm nothing broke**

Run: `cd backend && pytest tests/ -v`
Expected: All existing tests pass (no behavior change)

- [ ] **Step 4: Commit**

```bash
git add backend/app/providers/utils.py backend/app/providers/gemini.py
git commit -m "refactor: extract shared extract_json to providers/utils"
```

---

### Task 2: Add `openai` dependency

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Add `openai>=1.0` to dependencies**

In `pyproject.toml`, add `"openai>=1.0"` to the `dependencies` list.

- [ ] **Step 2: Install**

Run: `cd backend && pip install -e ".[dev]"`
Expected: openai package installed successfully

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore: add openai SDK dependency for Kimi provider"
```

---

### Task 3: Implement `KimiProvider`

**Files:**
- Create: `backend/app/providers/kimi.py`
- Create: `backend/tests/unit/test_kimi_provider.py`

- [ ] **Step 1: Write failing tests for KimiProvider**

```python
# backend/tests/unit/test_kimi_provider.py
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.kimi import KimiProvider


@pytest.fixture
def kimi_provider():
    return KimiProvider(api_key="sk-kimi-test-key")


def _mock_completion(content: str, input_tokens: int = 10, output_tokens: int = 20):
    """Build a mock ChatCompletion response."""
    mock = MagicMock()
    mock.choices = [MagicMock()]
    mock.choices[0].message.content = content
    mock.usage.prompt_tokens = input_tokens
    mock.usage.completion_tokens = output_tokens
    return mock


class TestKimiProviderProtocol:
    def test_has_name(self, kimi_provider):
        assert kimi_provider.name == "kimi"

    def test_has_generate_text(self, kimi_provider):
        assert hasattr(kimi_provider, "generate_text")
        assert callable(kimi_provider.generate_text)

    def test_has_analyze_content(self, kimi_provider):
        assert hasattr(kimi_provider, "analyze_content")
        assert callable(kimi_provider.analyze_content)


class TestGenerateText:
    @pytest.mark.asyncio
    async def test_returns_text(self, kimi_provider):
        mock_resp = _mock_completion("Hello world")
        with patch.object(
            kimi_provider, "_get_client"
        ) as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create = MagicMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client

            result = await kimi_provider.generate_text("Say hello")
            assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_extracts_json_when_schema(self, kimi_provider):
        json_str = json.dumps({"key": "value"})
        wrapped = f"```json\n{json_str}\n```"
        mock_resp = _mock_completion(wrapped)
        with patch.object(
            kimi_provider, "_get_client"
        ) as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create = MagicMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client

            result = await kimi_provider.generate_text("Give JSON", schema=dict)
            parsed = json.loads(result)
            assert parsed == {"key": "value"}

    @pytest.mark.asyncio
    async def test_returns_token_usage(self, kimi_provider):
        mock_resp = _mock_completion("text", input_tokens=50, output_tokens=100)
        with patch.object(
            kimi_provider, "_get_client"
        ) as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create = MagicMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client

            result = await kimi_provider.generate_text("test")
            assert kimi_provider.last_usage == {"input_tokens": 50, "output_tokens": 100}


class TestRetryBehavior:
    @pytest.mark.asyncio
    async def test_retries_on_invalid_json(self, kimi_provider):
        bad_resp = _mock_completion("not json")
        good_resp = _mock_completion('{"valid": true}')
        with patch.object(
            kimi_provider, "_get_client"
        ) as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create = MagicMock(
                side_effect=[bad_resp, good_resp]
            )
            mock_client_fn.return_value = mock_client

            result = await kimi_provider.generate_text("Give JSON", schema=dict)
            assert json.loads(result) == {"valid": True}
            assert mock_client.chat.completions.create.call_count == 2


class TestAnalyzeContent:
    @pytest.mark.asyncio
    async def test_combines_content_and_prompt(self, kimi_provider):
        mock_resp = _mock_completion("analysis result")
        with patch.object(
            kimi_provider, "_get_client"
        ) as mock_client_fn:
            mock_client = MagicMock()
            mock_client.chat.completions.create = MagicMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client

            result = await kimi_provider.analyze_content("video data", "analyze this")
            assert result == "analysis result"
            # Verify both content and prompt appear in the call
            call_args = mock_client.chat.completions.create.call_args
            messages = call_args[1]["messages"] if "messages" in call_args[1] else call_args[0][0]
            user_msg = messages[-1]["content"]
            assert "video data" in user_msg
            assert "analyze this" in user_msg
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_kimi_provider.py -v`
Expected: ImportError — `app.providers.kimi` does not exist

- [ ] **Step 3: Implement KimiProvider**

```python
# backend/app/providers/kimi.py
"""Kimi (Moonshot AI) reasoning provider via OpenAI-compatible API."""
import asyncio
import json

import structlog
from pydantic import BaseModel

from app.config import settings
from app.models.errors import InvalidResponseError, ProviderError, RateLimitError
from app.providers.utils import extract_json

logger = structlog.get_logger()

BACKOFF_SECS = [1, 2, 4]
MAX_RETRIES = 3

KIMI_BASE_URL = "https://api.kimi.com/coding/v1"
KIMI_MODEL = "kimi-for-coding/k2p5"
KIMI_USER_AGENT = "claude-code/0.1.0"


class KimiProvider:
    name = "kimi"

    def __init__(self, api_key: str | None = None, model: str = KIMI_MODEL):
        self._api_key = api_key or settings.kimi_api_key
        self._model = model
        self._client = None
        self.last_usage: dict[str, int] | None = None

    def _get_client(self):
        if self._client is None:
            import httpx
            from openai import OpenAI

            http_client = httpx.Client(
                headers={"User-Agent": KIMI_USER_AGENT},
                timeout=120.0,
            )
            self._client = OpenAI(
                api_key=self._api_key,
                base_url=KIMI_BASE_URL,
                http_client=http_client,
            )
        return self._client

    async def generate_text(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> str:
        client = self._get_client()
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=32768,
                )
                text = response.choices[0].message.content

                # Capture token usage
                if response.usage:
                    self.last_usage = {
                        "input_tokens": response.usage.prompt_tokens,
                        "output_tokens": response.usage.completion_tokens,
                    }

                if schema:
                    json_str = extract_json(text)
                    try:
                        json.loads(json_str)
                    except json.JSONDecodeError as e:
                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                "kimi_invalid_json",
                                attempt=attempt,
                                error=str(e),
                            )
                            continue
                        raise InvalidResponseError(
                            f"Failed to parse JSON after {MAX_RETRIES} attempts",
                            provider=self.name,
                            raw_response=text,
                        ) from e
                    return json_str
                return text

            except (InvalidResponseError, ProviderError, RateLimitError):
                raise
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            "kimi_rate_limit",
                            attempt=attempt,
                            backoff=BACKOFF_SECS[attempt],
                        )
                        await asyncio.sleep(BACKOFF_SECS[attempt])
                        continue
                    raise RateLimitError(
                        f"Rate limited after {MAX_RETRIES} retries",
                        provider=self.name,
                        retry_after=BACKOFF_SECS[-1] * 2,
                    ) from e
                raise ProviderError(
                    error_str,
                    provider=self.name,
                    status_code=getattr(e, "status_code", None),
                ) from e

        raise ProviderError("Unexpected retry exhaustion", provider=self.name)

    async def analyze_content(self, content: str, prompt: str) -> str:
        full_prompt = f"{prompt}\n\nContent to analyze:\n{content}"
        return await self.generate_text(full_prompt)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_kimi_provider.py -v`
Expected: All tests pass

- [ ] **Step 5: Run full suite to confirm no regressions**

Run: `cd backend && pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/kimi.py backend/tests/unit/test_kimi_provider.py
git commit -m "feat: add KimiProvider — OpenAI-compatible Kimi Code reasoning provider"
```

---

### Task 4: Implement UsageTracker

**Files:**
- Create: `backend/app/providers/usage.py`
- Create: `backend/tests/unit/test_usage_tracker.py`

- [ ] **Step 1: Write failing tests for UsageTracker**

```python
# backend/tests/unit/test_usage_tracker.py
import pytest

from app.providers.usage import UsageTracker


class TestUsageTracker:
    def test_record_request(self):
        tracker = UsageTracker()
        tracker.record("S1", input_tokens=100, output_tokens=200, latency_ms=1500)
        assert tracker.total_requests == 1
        assert tracker.total_input_tokens == 100
        assert tracker.total_output_tokens == 200

    def test_record_multiple_stages(self):
        tracker = UsageTracker()
        tracker.record("S1", input_tokens=100, output_tokens=200, latency_ms=1000)
        tracker.record("S1", input_tokens=150, output_tokens=250, latency_ms=1200)
        tracker.record("S3", input_tokens=80, output_tokens=500, latency_ms=3000)

        assert tracker.total_requests == 3
        assert tracker.total_input_tokens == 330
        assert tracker.total_output_tokens == 950

        s1 = tracker.stage_stats("S1")
        assert s1["requests"] == 2
        assert s1["input_tokens"] == 250
        assert s1["output_tokens"] == 450
        assert s1["avg_latency_ms"] == 1100

    def test_stage_stats_empty(self):
        tracker = UsageTracker()
        s1 = tracker.stage_stats("S1")
        assert s1["requests"] == 0

    def test_summary_table(self):
        tracker = UsageTracker()
        tracker.record("S1", input_tokens=100, output_tokens=200, latency_ms=1000)
        tracker.record("S3", input_tokens=80, output_tokens=500, latency_ms=3000)
        table = tracker.summary_table()
        assert "S1" in table
        assert "S3" in table
        assert "TOTAL" in table

    def test_progress_string(self):
        tracker = UsageTracker()
        tracker.record("S1", input_tokens=100, output_tokens=200, latency_ms=1000)
        progress = tracker.progress("S1", completed=5, total=100)
        assert "5/100" in progress
        assert "S1" in progress
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_usage_tracker.py -v`
Expected: ImportError — `app.providers.usage` does not exist

- [ ] **Step 3: Implement UsageTracker**

```python
# backend/app/providers/usage.py
"""Per-run LLM usage tracking with visual progress."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class _StageStats:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_latency_ms: int = 0


@dataclass
class UsageTracker:
    """Accumulates per-stage LLM usage for a single pipeline run."""

    _stages: dict[str, _StageStats] = field(default_factory=dict)

    def record(
        self,
        stage: str,
        input_tokens: int,
        output_tokens: int,
        latency_ms: int,
    ) -> None:
        if stage not in self._stages:
            self._stages[stage] = _StageStats()
        s = self._stages[stage]
        s.requests += 1
        s.input_tokens += input_tokens
        s.output_tokens += output_tokens
        s.total_latency_ms += latency_ms

    @property
    def total_requests(self) -> int:
        return sum(s.requests for s in self._stages.values())

    @property
    def total_input_tokens(self) -> int:
        return sum(s.input_tokens for s in self._stages.values())

    @property
    def total_output_tokens(self) -> int:
        return sum(s.output_tokens for s in self._stages.values())

    def stage_stats(self, stage: str) -> dict:
        s = self._stages.get(stage)
        if not s or s.requests == 0:
            return {"requests": 0, "input_tokens": 0, "output_tokens": 0, "avg_latency_ms": 0}
        return {
            "requests": s.requests,
            "input_tokens": s.input_tokens,
            "output_tokens": s.output_tokens,
            "avg_latency_ms": s.total_latency_ms // s.requests,
        }

    def progress(self, stage: str, completed: int, total: int) -> str:
        s = self._stages.get(stage)
        tokens = (s.input_tokens + s.output_tokens) if s else 0
        return f"[{stage}] {completed}/{total} requests ({tokens:,} tokens used)"

    def summary_table(self) -> str:
        header = f"{'Stage':<8} {'Reqs':>6} {'In Tok':>10} {'Out Tok':>10} {'Avg Lat':>10}"
        sep = "-" * len(header)
        lines = [header, sep]

        for stage_name in sorted(self._stages):
            s = self.stage_stats(stage_name)
            avg = f"{s['avg_latency_ms']}ms"
            lines.append(
                f"{stage_name:<8} {s['requests']:>6} "
                f"{s['input_tokens']:>10,} {s['output_tokens']:>10,} "
                f"{avg:>10}"
            )

        total_lat = sum(s.total_latency_ms for s in self._stages.values())
        total_req = self.total_requests
        avg_total = f"{total_lat // total_req}ms" if total_req else "0ms"
        lines.append(sep)
        lines.append(
            f"{'TOTAL':<8} {total_req:>6} "
            f"{self.total_input_tokens:>10,} {self.total_output_tokens:>10,} "
            f"{avg_total:>10}"
        )
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/unit/test_usage_tracker.py -v`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/app/providers/usage.py backend/tests/unit/test_usage_tracker.py
git commit -m "feat: add UsageTracker — per-stage request/token/latency stats"
```

---

### Task 5: Register Kimi + update CLI default

**Files:**
- Modify: `backend/app/providers/registry.py`
- Modify: `backend/app/runner/cli.py`
- Modify: `backend/tests/unit/test_provider_registry.py`

- [ ] **Step 1: Update registry test**

Add to `backend/tests/unit/test_provider_registry.py`:

```python
def test_list_providers_includes_kimi():
    providers = list_providers()
    assert "kimi" in providers["reasoning"]


def test_get_kimi_provider():
    provider = get_reasoning_provider("kimi")
    assert provider.name == "kimi"
    assert hasattr(provider, "generate_text")
    assert hasattr(provider, "analyze_content")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/unit/test_provider_registry.py -v`
Expected: `test_list_providers_includes_kimi` and `test_get_kimi_provider` FAIL

- [ ] **Step 3: Register kimi in registry**

Update `backend/app/providers/registry.py`:

```python
from app.providers.gemini import GeminiProvider
from app.providers.kimi import KimiProvider

_reasoning_providers: dict[str, type] = {
    "gemini": GeminiProvider,
    "kimi": KimiProvider,
}
```

- [ ] **Step 4: Update CLI default to kimi**

In `backend/app/runner/cli.py`, change:

```python
parser.add_argument("--provider", default="kimi", help="Reasoning provider (default: kimi)")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd backend && pytest tests/ -v`
Expected: All tests pass (including new kimi registry tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/providers/registry.py backend/app/runner/cli.py backend/tests/unit/test_provider_registry.py
git commit -m "feat: register KimiProvider as default reasoning provider"
```

---

### Task 6: Integrate UsageTracker into local_runner

**Files:**
- Modify: `backend/app/runner/local_runner.py`
- Modify: `backend/app/runner/cli.py`

- [ ] **Step 1: Add tracking wrapper to local_runner**

Update `backend/app/runner/local_runner.py` to accept an optional `UsageTracker`, wrap provider calls to capture usage after each call, and log progress.

The key change: after each `provider.generate_text()` call in the runner loop, check `provider.last_usage` and record it. This means the runner needs to know about `last_usage` — which both `KimiProvider` and `GeminiProvider` should expose.

Add `last_usage` tracking to `local_runner.py`:

```python
from app.providers.usage import UsageTracker

async def run_pipeline(
    config: PipelineConfig,
    videos: list[VideoInput],
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
    num_scripts: int | None = None,
    num_personas: int | None = None,
    top_n: int | None = None,
    tracker: UsageTracker | None = None,
) -> S6Output:
    _num_scripts = num_scripts or settings.s3_script_count
    _num_personas = num_personas or settings.s4_persona_count
    _top_n = top_n or settings.s6_top_n
    _tracker = tracker or UsageTracker()

    logger.info("pipeline_start", run_id=config.run_id, videos=len(videos))

    # S1: Analyze all videos
    logger.info("s1_start", count=len(videos))
    patterns = []
    for i, video in enumerate(videos):
        pattern = await s1_analyze(video, provider)
        _record_usage(_tracker, "S1", provider)
        patterns.append(pattern)
        logger.info("s1_progress", completed=i + 1, total=len(videos),
                     usage=_tracker.progress("S1", i + 1, len(videos)))
    logger.info("s1_complete", patterns=len(patterns))

    # S2: Aggregate (no LLM)
    logger.info("s2_start")
    library = s2_aggregate(patterns)
    logger.info("s2_complete", pattern_types=len(library.patterns))

    # S3: Generate scripts
    logger.info("s3_start", target=_num_scripts)
    scripts = await s3_generate(library, provider, feedback, num_scripts=_num_scripts)
    # S3 makes multiple calls internally — estimate from provider.last_usage
    _record_usage(_tracker, "S3", provider)
    logger.info("s3_complete", scripts=len(scripts))

    # S4: Vote
    logger.info("s4_start", personas=_num_personas)
    votes = []
    for i in range(_num_personas):
        vote = await s4_vote(scripts, f"persona_{i}", provider, feedback)
        _record_usage(_tracker, "S4", provider)
        votes.append(vote)
        logger.info("s4_progress", completed=i + 1, total=_num_personas,
                     usage=_tracker.progress("S4", i + 1, _num_personas))
    logger.info("s4_complete", votes=len(votes))

    # S5: Rank (no LLM)
    logger.info("s5_start")
    rankings = s5_rank(votes, top_n=_top_n)
    logger.info("s5_complete", top_scripts=[r.script_id for r in rankings.top_10])

    # S6: Personalize top N
    actual_top_n = min(_top_n, len(rankings.top_10))
    logger.info("s6_start", count=actual_top_n)
    results = []
    for i, ranked in enumerate(rankings.top_10[:actual_top_n]):
        script = next((s for s in scripts if s.script_id == ranked.script_id), None)
        if script is None:
            logger.warning("script_not_found", script_id=ranked.script_id)
            continue
        result = await s6_personalize(script, config.creator_profile, provider)
        _record_usage(_tracker, "S6", provider)
        result.rank = ranked.rank
        result.vote_score = ranked.score
        results.append(result)
        logger.info("s6_progress", completed=i + 1, total=actual_top_n,
                     usage=_tracker.progress("S6", i + 1, actual_top_n))
    logger.info("s6_complete", results=len(results))

    # Print usage summary
    logger.info("usage_summary", table="\n" + _tracker.summary_table())

    output = S6Output(
        run_id=config.run_id,
        results=results,
        creator_profile=config.creator_profile,
        completed_at=datetime.now(UTC),
    )

    logger.info("pipeline_complete", run_id=config.run_id, results=len(results))
    return output


def _record_usage(tracker: UsageTracker, stage: str, provider) -> None:
    """Capture last_usage from provider if available."""
    usage = getattr(provider, "last_usage", None)
    if usage:
        tracker.record(
            stage,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            latency_ms=0,  # TODO: add timing wrapper
        )
```

- [ ] **Step 2: Add `last_usage` to GeminiProvider for consistency**

In `backend/app/providers/gemini.py`, add `self.last_usage = None` in `__init__` and after getting a response, capture token counts if available. Gemini's `google-genai` response has `usage_metadata`:

```python
# In __init__:
self.last_usage: dict[str, int] | None = None

# After getting response in generate_text, before returning:
if hasattr(response, "usage_metadata") and response.usage_metadata:
    self.last_usage = {
        "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
        "output_tokens": getattr(response.usage_metadata, "candidates_token_count", 0),
    }
```

- [ ] **Step 3: Run full test suite**

Run: `cd backend && pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/app/runner/local_runner.py backend/app/runner/cli.py backend/app/providers/gemini.py
git commit -m "feat: integrate UsageTracker into pipeline runner with progress logging"
```

---

### Task 7: Update `.env.example` + lint + final check

**Files:**
- Modify: `backend/.env.example`

- [ ] **Step 1: Add kimi key to `.env.example`**

Add line: `FLAIR2_KIMI_API_KEY=sk-kimi-your-key-here`

- [ ] **Step 2: Run linter**

Run: `cd backend && ruff check . && ruff format .`
Expected: Clean

- [ ] **Step 3: Run full test suite**

Run: `cd backend && pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/.env.example
git commit -m "docs: add FLAIR2_KIMI_API_KEY to .env.example"
```
