# Architecture Design — AI Campaign Studio V2 (flair2)

| | |
|---|---|
| **Authors** | Sam Wu · Jess · Shannon |
| **Version** | v3.0 — March 2026 |
| **Status** | Approved — ready for implementation |
| **Spec** | `design/spec_v3.md` (v3.2) |
| **Supersedes** | `design/architecture.md`, `design/architecture_v2.md` |

---

## 1. Architectural Decisions

Six decisions made during design review. Each is grounded in a principle — if the context changes, revisit the decision, not the principle.

| # | Decision | Choice | Principle |
|---|----------|--------|-----------|
| 1 | MVP ↔ Distributed relationship | MVP is local mode of the distributed codebase | Write once, run anywhere |
| 2 | Stage communication | Pure functions: `input → output`, no side effects | Testability, portability |
| 3 | Module layering | 4-layer: API → Pipeline → Providers → Infra | Separation of concerns |
| 4 | Error handling | Typed exception hierarchy with structured context | Pattern-match on failure type for retry/halt/alert |
| 5 | Orchestrator | Explicit state machine in Redis | Visible, debuggable, inspectable (DDIA: make data flow explicit) |
| 6 | Worker model | Generic workers, any task type | YAGNI — LLM rate limit is the ceiling, not worker count |

---

## 2. System Architecture

### 2.1 Overview

```
                    ┌─────────────────┐
                    │ Cloudflare Pages │  (Frontend)
                    │  Astro + React   │
                    └────────┬────────┘
                             │ HTTPS (REST + SSE)
                             ▼
                    ┌─────────────────┐
                    │       ALB       │
                    └───┬─────────┬───┘
                        │         │
                   ┌────▼──┐ ┌───▼───┐
                   │ECS API│ │ECS API│  (FastAPI)
                   └───┬───┘ └───┬───┘
                       │         │
          ┌────────────┼─────────┼────────────┐
          │            │         │             │
          ▼            ▼         ▼             ▼
   ┌───────────┐ ┌──────────┐ ┌───┐  ┌────────────┐
   │ElastiCache│ │ECS Worker│ │ S3│  │  DynamoDB   │
   │  (Redis)  │ │(Celery×N)│ │   │  │            │
   └───────────┘ └──────────┘ └───┘  └────────────┘
                                 ▲
                                 │
                           ┌─────┴─────┐
                           │  Lambda   │  (S7 video)
                           └───────────┘
```

**8 AWS Services:** ECS Fargate, ALB, ElastiCache (Redis), S3, DynamoDB, Lambda, CloudWatch, IAM.

### 2.2 Four-Layer Architecture

Dependencies flow downward only. No layer imports from a layer above it.

```
┌─────────────────────────────────────────┐
│  Layer 1: API                           │  FastAPI routes, SSE, sessions
│  app/api/                               │  Depends on: Pipeline, Infra
├─────────────────────────────────────────┤
│  Layer 2: Pipeline                      │  Orchestrator, pure stage functions,
│  app/pipeline/                          │  prompts, Celery task wrappers
│                                         │  Depends on: Providers, Infra
├─────────────────────────────────────────┤
│  Layer 3: Providers                     │  LLM + Video provider interfaces
│  app/providers/                         │  Depends on: Infra (rate limiter)
├─────────────────────────────────────────┤
│  Layer 4: Infra                         │  Redis, S3, DynamoDB, config
│  app/infra/                             │  Depends on: nothing internal
└─────────────────────────────────────────┘

  Shared across all layers:
  app/models/    ← Pydantic models (data contracts)
```

### 2.3 Local Mode vs Distributed Mode

The same stage functions execute in both modes. Only the execution layer changes.

| Aspect | Local Mode (MVP) | Distributed Mode |
|--------|-----------------|-----------------|
| Entry point | `app/runner/local_runner.py` | `app/main.py` (FastAPI) |
| Stage execution | Direct function calls, sequential | Celery tasks, parallel for S1/S4 |
| State storage | In-memory (function return values) | Redis (per-run namespaced keys) |
| Output storage | Local JSON file | S3 + DynamoDB |
| Rate limiting | None (single-user) | Redis token bucket |
| SSE streaming | None | Redis event queue → SSE endpoint |
| Dependencies | Python + LLM API key | + Redis + Celery + AWS services |

---

## 3. Directory Structure

```
flair2/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app entry point
│   │   ├── config.py                  # pydantic-settings, env-based config
│   │   │
│   │   ├── api/                       # ── Layer 1: API ──
│   │   │   ├── __init__.py
│   │   │   ├── deps.py                # Dependency injection (providers, redis, etc.)
│   │   │   └── routes/
│   │   │       ├── pipeline.py        # POST /api/pipeline/start
│   │   │       │                      # GET  /api/pipeline/status/{run_id} (SSE)
│   │   │       │                      # GET  /api/pipeline/results/{run_id}
│   │   │       ├── video.py           # POST /api/video/generate
│   │   │       │                      # GET  /api/video/status/{run_id}/{job_id}
│   │   │       ├── performance.py     # POST /api/performance
│   │   │       │                      # GET  /api/performance/{run_id}
│   │   │       │                      # GET  /api/insights
│   │   │       ├── runs.py            # GET  /api/runs
│   │   │       ├── providers.py       # GET  /api/providers
│   │   │       └── health.py          # GET  /api/health
│   │   │
│   │   ├── pipeline/                  # ── Layer 2: Pipeline ──
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py        # State machine, stage transitions
│   │   │   ├── stages/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── s1_analyze.py      # VideoInput → S1Pattern
│   │   │   │   ├── s2_aggregate.py    # list[S1Pattern] → S2PatternLibrary
│   │   │   │   ├── s3_generate.py     # S2PatternLibrary → list[CandidateScript]
│   │   │   │   ├── s4_vote.py         # list[CandidateScript] → PersonaVote
│   │   │   │   ├── s5_rank.py         # list[PersonaVote] → S5Rankings
│   │   │   │   └── s6_personalize.py  # CandidateScript + CreatorProfile → FinalResult
│   │   │   └── prompts/
│   │   │       ├── __init__.py
│   │   │       ├── s1_prompts.py      # Structural pattern extraction prompts
│   │   │       ├── s3_prompts.py      # Script generation prompts (+ feedback injection)
│   │   │       ├── s4_prompts.py      # Persona evaluation prompts (+ feedback injection)
│   │   │       └── s6_prompts.py      # Style injection + video prompt generation
│   │   │
│   │   ├── providers/                 # ── Layer 3: Providers ──
│   │   │   ├── __init__.py
│   │   │   ├── base.py                # ReasoningProvider, VideoProvider protocols
│   │   │   ├── registry.py            # Provider name → instance lookup
│   │   │   ├── gemini.py              # Google Gemini implementation
│   │   │   ├── kimi.py                # Kimi 2.5 implementation
│   │   │   ├── openai_provider.py     # OpenAI GPT-4o-mini implementation
│   │   │   ├── seedance.py            # Seedance 2.0 via PiAPI
│   │   │   └── veo.py                 # Google Veo implementation
│   │   │
│   │   ├── infra/                     # ── Layer 4: Infra ──
│   │   │   ├── __init__.py
│   │   │   ├── redis_client.py        # All Redis access (namespaced by run_id)
│   │   │   ├── dynamo_client.py       # All DynamoDB access
│   │   │   ├── s3_client.py           # All S3 access + presigned URL generation
│   │   │   └── rate_limiter.py        # Token bucket implementation in Redis
│   │   │
│   │   ├── workers/                   # ── Celery (distributed mode only) ──
│   │   │   ├── __init__.py
│   │   │   ├── celery_app.py          # Celery config, broker = Redis
│   │   │   └── tasks.py               # Thin wrappers: read → call stage fn → write
│   │   │
│   │   ├── sse/                       # ── Server-Sent Events ──
│   │   │   ├── __init__.py
│   │   │   └── manager.py             # SSE event broadcasting per run_id
│   │   │
│   │   ├── models/                    # ── Shared Pydantic models ──
│   │   │   ├── __init__.py
│   │   │   ├── pipeline.py            # PipelineRun, PipelineConfig, CreatorProfile
│   │   │   ├── stages.py              # S1Pattern, S2PatternLibrary, CandidateScript, etc.
│   │   │   ├── performance.py         # VideoPerformance
│   │   │   └── errors.py              # PipelineError hierarchy
│   │   │
│   │   └── runner/                    # ── Local mode (MVP) ──
│   │       ├── __init__.py
│   │       └── local_runner.py        # Runs pipeline without Redis/Celery
│   │
│   ├── tests/
│   │   ├── conftest.py                # Shared fixtures, provider mocks
│   │   ├── fixtures/                  # Sample video inputs, expected outputs
│   │   │   ├── sample_video_input.json
│   │   │   ├── sample_s1_pattern.json
│   │   │   └── sample_creator_profile.json
│   │   ├── unit/
│   │   │   ├── test_s1_analyze.py
│   │   │   ├── test_s2_aggregate.py
│   │   │   ├── test_s3_generate.py
│   │   │   ├── test_s4_vote.py
│   │   │   ├── test_s5_rank.py
│   │   │   ├── test_s6_personalize.py
│   │   │   ├── test_orchestrator.py
│   │   │   ├── test_rate_limiter.py
│   │   │   └── test_provider_registry.py
│   │   └── integration/
│   │       ├── test_pipeline_local.py     # Full pipeline in local mode
│   │       └── test_redis_state.py        # Orchestrator state transitions with real Redis
│   │
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── docker-compose.yml             # Local dev: Redis + API + Celery worker
│
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── index.astro            # Landing
│   │   │   ├── create.astro           # Input form + model selection
│   │   │   ├── pipeline/[id].astro    # Real-time stage progress (SSE)
│   │   │   ├── vote/[id].astro        # Voting animation (SSE)
│   │   │   ├── results/[id].astro     # Scripts + video player
│   │   │   ├── track/[id].astro       # Performance data entry
│   │   │   ├── insights.astro         # Performance dashboard
│   │   │   └── runs.astro             # Run history
│   │   ├── components/
│   │   │   ├── PipelineVisualizer.tsx  # React island — SSE-connected
│   │   │   ├── VotingAnimation.tsx     # React island — 100 avatar grid
│   │   │   └── VideoPlayer.tsx         # React island — presigned URL playback
│   │   ├── lib/
│   │   │   ├── api-client.ts          # Single module for all backend calls
│   │   │   └── sse-client.ts          # SSE connection hook
│   │   └── styles/
│   ├── astro.config.mjs
│   ├── package.json
│   └── tsconfig.json
│
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   ├── modules/
│   │   ├── ecs/                       # API service + worker service
│   │   ├── alb/                       # Load balancer + target groups
│   │   ├── elasticache/               # Redis single node
│   │   ├── dynamodb/                  # pipeline_runs + video_performance tables
│   │   ├── s3/                        # flair2-pipeline bucket
│   │   ├── lambda/                    # S7 video generation function
│   │   └── iam/                       # Least-privilege roles
│   └── environments/
│       ├── dev.tfvars
│       └── prod.tfvars
│
├── design/                            # Specs, architecture, research
├── data/                              # Dataset files (gitignored)
├── .github/workflows/ci.yml           # Lint + test on push
├── CLAUDE.md
└── .gitignore
```

---

## 4. Data Models

All models live in `app/models/`. They are the typed contracts between every layer of the system.

### 4.1 Pipeline Models

```python
# models/pipeline.py

from datetime import datetime
from enum import Enum
from pydantic import BaseModel


class CreatorProfile(BaseModel):
    tone: str                           # "casual", "professional", "edgy"
    vocabulary: list[str]               # Words/phrases the creator uses
    catchphrases: list[str]             # Signature expressions
    topics_to_avoid: list[str]          # Content boundaries


class PipelineConfig(BaseModel):
    run_id: str                         # UUID
    session_id: str                     # Browser session
    reasoning_model: str                # "gemini" | "kimi" | "openai"
    video_model: str | None             # "seedance" | "veo" | None (skip)
    creator_profile: CreatorProfile


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineRun(BaseModel):
    run_id: str
    session_id: str
    status: PipelineStatus
    config: PipelineConfig
    current_stage: str | None           # "S1_MAP", "S2_RED", etc.
    stages: dict[str, StageStatus]      # Per-stage status tracking
    created_at: datetime
    completed_at: datetime | None
    s3_results_key: str | None          # Path in S3
    error: str | None                   # Last error message
```

### 4.2 Stage Models

```python
# models/stages.py

from pydantic import BaseModel


# ── S1: Analyze ──────────────────────────────────────────

class VideoInput(BaseModel):
    video_id: str
    transcript: str | None              # ASR transcript (English)
    description: str | None             # Caption / description text
    duration: float                     # Seconds
    engagement: dict                    # {"views": N, "likes": N, ...}


class S1Pattern(BaseModel):
    video_id: str
    hook_type: str                      # "question" | "shock" | "story" | "direct_address"
    pacing: str                         # "fast_slow_fast" | "escalating" | "steady"
    emotional_arc: str                  # "negative_to_positive" | "curiosity_gap" | ...
    pattern_interrupts: list[str]       # Techniques used to maintain attention
    retention_mechanics: list[str]      # Open loops, payoff delays, etc.
    engagement_triggers: list[str]      # What drives likes/shares/comments
    structure_notes: str                # Free-form structural analysis


# ── S2: Aggregate ────────────────────────────────────────

class PatternEntry(BaseModel):
    pattern_type: str                   # e.g. "question_hook + fast_slow_fast"
    frequency: int                      # How many videos used this pattern
    examples: list[str]                 # Video IDs as examples
    avg_engagement: float               # Average engagement score


class S2PatternLibrary(BaseModel):
    patterns: list[PatternEntry]        # Sorted by frequency descending
    total_videos_analyzed: int


# ── S3: Generate ─────────────────────────────────────────

class CandidateScript(BaseModel):
    script_id: str                      # UUID
    pattern_used: str                   # Which pattern from the library
    hook: str                           # The opening hook text
    body: str                           # Main content
    payoff: str                         # Closing / payoff
    estimated_duration: float           # Target seconds
    structural_notes: str               # Why this structure was chosen


# ── S4: Vote ─────────────────────────────────────────────

class PersonaVote(BaseModel):
    persona_id: str                     # "persona_0" .. "persona_99"
    persona_description: str            # Generated persona background
    top_5_script_ids: list[str]         # Ordered preference
    reasoning: str                      # Why these 5


# ── S5: Rank ─────────────────────────────────────────────

class RankedScript(BaseModel):
    script_id: str
    vote_count: int
    score: float                        # Weighted score
    rank: int                           # 1-10


class S5Rankings(BaseModel):
    top_10: list[RankedScript]
    total_votes_cast: int


# ── S6: Personalize ──────────────────────────────────────

class FinalResult(BaseModel):
    script_id: str
    original_script: CandidateScript
    personalized_script: str            # Rewritten in creator's voice
    video_prompt: str                   # Structured prompt for video gen
    rank: int
    vote_score: float


class S6Output(BaseModel):
    run_id: str
    results: list[FinalResult]          # Exactly 10
    creator_profile: CreatorProfile
    completed_at: datetime
```

### 4.3 Performance Tracking Models

```python
# models/performance.py

from datetime import datetime
from pydantic import BaseModel


class VideoPerformance(BaseModel):
    run_id: str
    script_id: str
    platform: str                       # "tiktok" | "youtube" | "instagram"
    post_url: str
    posted_at: datetime
    views: int
    likes: int
    comments: int
    shares: int
    watch_time_avg: float | None        # Seconds
    completion_rate: float | None       # 0-100
    committee_rank: int                 # What S4/S5 predicted (1-10)
    script_pattern: str                 # Hook type used (for correlation)
```

### 4.4 Error Hierarchy

```python
# models/errors.py


class PipelineError(Exception):
    """Base — all pipeline errors inherit this."""
    def __init__(
        self,
        message: str,
        run_id: str | None = None,
        stage: str | None = None,
        attempt: int | None = None,
    ):
        self.run_id = run_id
        self.stage = stage
        self.attempt = attempt
        super().__init__(message)


class ProviderError(PipelineError):
    """LLM/Video API failure — retryable."""
    def __init__(self, message: str, provider: str, status_code: int | None = None, **kwargs):
        self.provider = provider
        self.status_code = status_code
        super().__init__(message, **kwargs)


class RateLimitError(ProviderError):
    """Rate limit hit — backoff and retry."""
    def __init__(self, message: str, retry_after: float | None = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class InvalidResponseError(ProviderError):
    """LLM returned unparseable output — retry with stricter prompt."""
    def __init__(self, message: str, raw_response: str, **kwargs):
        self.raw_response = raw_response
        super().__init__(message, **kwargs)


class StageError(PipelineError):
    """Pipeline logic failure — halt the stage."""
    pass


class InfraError(PipelineError):
    """Redis/S3/DynamoDB failure — alert and retry."""
    def __init__(self, message: str, service: str, **kwargs):
        self.service = service
        super().__init__(message, **kwargs)
```

---

## 5. Provider Interfaces

### 5.1 Protocol Classes

```python
# providers/base.py

from typing import Protocol
from pydantic import BaseModel


class ReasoningProvider(Protocol):
    """Any LLM that generates text."""

    name: str

    async def generate_text(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> str:
        """Generate text. If schema is provided, constrain output to JSON matching it."""
        ...

    async def analyze_content(
        self,
        content: str,
        prompt: str,
    ) -> str:
        """Analyze content (transcript/description) with a prompt."""
        ...


class VideoProvider(Protocol):
    """Any service that generates video clips."""

    name: str

    async def generate_video(
        self,
        prompt: str,
        duration: int = 6,
    ) -> bytes:
        """Submit video generation. Returns video bytes (mp4)."""
        ...

    async def check_status(
        self,
        job_id: str,
    ) -> VideoJobStatus:
        """Poll async video generation status."""
        ...


class VideoJobStatus(BaseModel):
    job_id: str
    status: str                         # "processing" | "complete" | "failed"
    video_url: str | None
    error: str | None
```

### 5.2 Provider Registry

```python
# providers/registry.py

_reasoning_providers: dict[str, type] = {}
_video_providers: dict[str, type] = {}


def register_reasoning(name: str, cls: type):
    _reasoning_providers[name] = cls

def register_video(name: str, cls: type):
    _video_providers[name] = cls

def get_reasoning_provider(name: str, **kwargs) -> ReasoningProvider:
    return _reasoning_providers[name](**kwargs)

def get_video_provider(name: str, **kwargs) -> VideoProvider:
    return _video_providers[name](**kwargs)

def list_providers() -> dict:
    return {
        "reasoning": list(_reasoning_providers.keys()),
        "video": list(_video_providers.keys()),
    }
```

---

## 6. Stage Function Signatures

Every stage is a pure async function. No Redis, no Celery, no side effects. Input → Output.

```python
# pipeline/stages/s1_analyze.py
async def s1_analyze(
    video: VideoInput,
    provider: ReasoningProvider,
) -> S1Pattern:
    """Extract structural patterns from one video."""

# pipeline/stages/s2_aggregate.py
def s2_aggregate(
    patterns: list[S1Pattern],
) -> S2PatternLibrary:
    """Merge patterns into ranked library. No LLM — pure algorithmic."""

# pipeline/stages/s3_generate.py
async def s3_generate(
    library: S2PatternLibrary,
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
) -> list[CandidateScript]:
    """Generate 50 candidate scripts. Sequential — deliberate bottleneck.
    Feedback (when available) calibrates which patterns to favor."""

# pipeline/stages/s4_vote.py
async def s4_vote(
    scripts: list[CandidateScript],
    persona_id: str,
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
) -> PersonaVote:
    """One persona evaluates all scripts, picks top 5.
    Feedback (when available) calibrates persona evaluation criteria."""

# pipeline/stages/s5_rank.py
def s5_rank(
    votes: list[PersonaVote],
) -> S5Rankings:
    """Aggregate votes into ranked top 10. No LLM — pure algorithmic."""

# pipeline/stages/s6_personalize.py
async def s6_personalize(
    script: CandidateScript,
    profile: CreatorProfile,
    provider: ReasoningProvider,
) -> FinalResult:
    """Rewrite script in creator's voice + generate video prompt."""
```

**Key design notes:**
- S2 and S5 are synchronous (no `async`) — they're pure algorithmic, no LLM calls.
- S3 and S4 accept optional `feedback` — historical performance data for pipeline calibration. `None` on first run.
- Prompts live in `pipeline/prompts/`, separate from stage logic. Stage functions import prompt templates and format them with inputs.

---

## 7. Orchestrator State Machine

### 7.1 States and Transitions

```
PENDING ──start()──► S1_MAP ──all 100──► S2_REDUCE ──done──► S3_SEQUENTIAL
                       │                                          │
                   on failure                                all 50 done
                       │                                          │
                       ▼                                          ▼
                    FAILED ◄─── any unrecoverable ──── S4_MAP ──all 100──► S5_REDUCE
                                                                              │
                                                                           done
                                                                              │
                                                                              ▼
                                                                        S6_PERSONALIZE
                                                                              │
                                                                         all 10 done
                                                                              │
                                                                              ▼
                                                                         COMPLETED
```

### 7.2 Transition Logic

```python
# pipeline/orchestrator.py

class PipelineOrchestrator:
    def __init__(self, redis: RedisClient):
        self.redis = redis

    async def start(self, config: PipelineConfig) -> None:
        """Initialize run state and enqueue S1 tasks."""

    async def on_s1_complete(self, run_id: str, video_id: str) -> None:
        """Called after each S1 task. Increments counter.
        When counter == 100, transitions to S2_REDUCE."""

    async def on_s2_complete(self, run_id: str) -> None:
        """Pattern library ready. Transitions to S3_SEQUENTIAL."""

    async def on_s3_complete(self, run_id: str) -> None:
        """50 scripts ready. Enqueues 100 S4 tasks.
        Transitions to S4_MAP."""

    async def on_s4_complete(self, run_id: str, persona_id: str) -> None:
        """Called after each S4 task. Increments counter.
        When counter == 100, transitions to S5_REDUCE."""

    async def on_s5_complete(self, run_id: str) -> None:
        """Top 10 ranked. Transitions to S6_PERSONALIZE."""

    async def on_s6_complete(self, run_id: str) -> None:
        """All 10 personalized. Writes to S3/DynamoDB.
        Transitions to COMPLETED. Sends SSE completion event."""

    async def on_failure(self, run_id: str, error: PipelineError) -> None:
        """Handle failure: checkpoint, log, SSE error event.
        Retry if ProviderError, halt if StageError, alert if InfraError."""
```

### 7.3 Redis Keys (per run)

```
# ── Run State ────────────────────────────────────
run:{run_id}:stage              STRING   Current state name (S1_MAP, S2_REDUCE, ...)
run:{run_id}:config             STRING   JSON PipelineConfig
run:{run_id}:status             STRING   "pending" | "running" | "completed" | "failed"

# ── Stage Completion Counters ────────────────────
run:{run_id}:s1:done            STRING   Integer counter (INCR on each S1 completion)
run:{run_id}:s4:done            STRING   Integer counter (INCR on each S4 completion)
run:{run_id}:s6:done            STRING   Integer counter (INCR on each S6 completion)

# ── Stage Results ────────────────────────────────
result:s1:{run_id}:{video_id}   STRING   JSON S1Pattern
pattern_library:{run_id}        STRING   JSON S2PatternLibrary
scripts:candidates:{run_id}     STRING   JSON list[CandidateScript]
result:s4:{run_id}:{persona_id} STRING   JSON PersonaVote
top_scripts:{run_id}            STRING   JSON S5Rankings
results:final:{run_id}          STRING   JSON S6Output

# ── Checkpointing ───────────────────────────────
checkpoint:{run_id}:{stage}     STRING   Last completed task index (for recovery)

# ── SSE Events ───────────────────────────────────
sse:events:{run_id}             LIST     SSE event queue (RPUSH/BLPOP)

# ── Global (shared across runs) ─────────────────
cache:{provider}:{prompt_hash}  STRING   SETNX-protected shared LLM result cache
ratelimit:{provider}            STRING   Token bucket counter (with TTL)

# ── Session Tracking ────────────────────────────
session:{session_id}:runs       LIST     run_ids belonging to this session
```

---

## 8. Storage Architecture

### 8.1 Three Stores, Three Purposes

| Store | Purpose | Lifetime | Access Pattern |
|-------|---------|----------|---------------|
| **Redis** (ElastiCache) | In-flight pipeline state, task queues, caching, rate limiting | Ephemeral — lost on restart | High-frequency small reads/writes, BRPOP blocking, SETNX atomic |
| **S3** | Pipeline output files (results JSON, video mp4s), input dataset | Permanent | Write once at end of pipeline, read by presigned URL |
| **DynamoDB** | Run metadata, performance tracking | Permanent, queryable | GetItem by run_id, Query by session_id, Scan for insights |

### 8.2 S3 Bucket Structure

```
s3://flair2-pipeline/
  dataset/
    videos/                              # Kuaishou/TikTok input data
  runs/
    {run_id}/
      config.json                        # PipelineConfig (~1KB)
      results.json                       # S6Output — 10 scripts + prompts (~50KB)
      videos/
        {script_id}.mp4                  # Generated video clips (~2-10MB each)
```

### 8.3 DynamoDB Tables

**Table: `pipeline_runs`**

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `run_id` | String | PK | UUID |
| `session_id` | String | GSI-PK | Browser session |
| `status` | String | — | pending / running / completed / failed |
| `config` | Map | — | PipelineConfig as JSON |
| `s3_results_key` | String | — | S3 path to results.json |
| `s3_video_keys` | Map | — | `{ script_id: s3_key }` |
| `created_at` | String | GSI-SK | ISO 8601 |
| `completed_at` | String | — | ISO 8601 or null |

**Table: `video_performance`**

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `run_id` | String | PK | Which pipeline run |
| `script_id` | String | SK | Which script |
| `platform` | String | — | tiktok / youtube / instagram |
| `post_url` | String | — | Link to post |
| `posted_at` | String | — | ISO 8601 |
| `views` | Number | — | |
| `likes` | Number | — | |
| `comments` | Number | — | |
| `shares` | Number | — | |
| `watch_time_avg` | Number | — | Seconds |
| `completion_rate` | Number | — | 0-100 |
| `committee_rank` | Number | — | S5 prediction |
| `script_pattern` | String | — | Hook type for correlation |

---

## 9. Infrastructure Design

### 9.1 Rate Limiter

Token bucket in Redis, global per provider. All users share the same bucket.

```python
# infra/rate_limiter.py

class TokenBucketRateLimiter:
    def __init__(self, redis: Redis, provider: str, max_tokens: int, window_seconds: int):
        self.key = f"ratelimit:{provider}"
        ...

    async def acquire(self) -> bool:
        """Try to consume a token. Returns True if allowed, False if rate limited.
        Uses INCR + EXPIRE atomically."""

    async def wait_for_token(self, max_wait: float = 30.0) -> None:
        """Block until a token is available. Exponential backoff with jitter."""
```

### 9.2 SETNX Cache

Cross-user shared cache for LLM results. Keyed by prompt hash, not run_id.

```python
# infra/redis_client.py (cache methods)

async def cache_get_or_compute(
    self,
    cache_key: str,
    compute_fn: Callable[[], Awaitable[str]],
    ttl: int = 3600,
) -> str:
    """SETNX pattern: if key exists, return cached value.
    If not, set 'computing' sentinel, call compute_fn, store result.
    Other callers wait for result to appear."""
```

### 9.3 Checkpoint Recovery

```python
# infra/redis_client.py (checkpoint methods)

async def write_checkpoint(self, run_id: str, stage: str, index: int) -> None:
    """Write last completed task index."""

async def read_checkpoint(self, run_id: str, stage: str) -> int | None:
    """Read checkpoint. Returns None if no checkpoint exists (fresh start)."""
```

---

## 10. Execution Modes

### 10.1 Local Runner (MVP)

```python
# runner/local_runner.py

async def run_pipeline(
    config: PipelineConfig,
    videos: list[VideoInput],
    provider: ReasoningProvider,
    feedback: list[VideoPerformance] | None = None,
) -> S6Output:
    """Run full pipeline locally. No Redis, no Celery.
    Same stage functions as distributed mode."""

    # S1: Analyze all videos (sequential)
    patterns = [await s1_analyze(v, provider) for v in videos]

    # S2: Aggregate (algorithmic)
    library = s2_aggregate(patterns)

    # S3: Generate 50 scripts (sequential)
    scripts = await s3_generate(library, provider, feedback)

    # S4: 100 persona votes (sequential)
    votes = [await s4_vote(scripts, f"persona_{i}", provider, feedback)
             for i in range(100)]

    # S5: Rank (algorithmic)
    rankings = s5_rank(votes)

    # S6: Personalize top 10
    results = [await s6_personalize(find_script(scripts, r), config.creator_profile, provider)
               for r in rankings.top_10]

    return S6Output(run_id=config.run_id, results=results,
                    creator_profile=config.creator_profile, completed_at=datetime.utcnow())
```

### 10.2 Celery Tasks (Distributed)

```python
# workers/tasks.py

@celery_app.task(bind=True, max_retries=3)
def s1_analyze_task(self, run_id: str, video_json: str):
    """Thin wrapper: deserialize → call pure function → serialize → store."""
    video = VideoInput.model_validate_json(video_json)
    provider = get_provider_for_run(run_id)

    try:
        result = asyncio.run(s1_analyze(video, provider))
    except ProviderError as e:
        self.retry(countdown=backoff(self.request.retries))

    redis.set(f"result:s1:{run_id}:{video.video_id}", result.model_dump_json())
    done = redis.incr(f"run:{run_id}:s1:done")

    if done == 100:
        orchestrator.on_s1_complete(run_id)
```

---

## 11. Testing Strategy

### 11.1 Test Pyramid

| Level | What | How | Count |
|-------|------|-----|-------|
| **Unit** | Each stage function, rate limiter, orchestrator transitions | Mock provider (returns canned responses), assert on Pydantic output | 1 per stage + infra module |
| **Integration** | Full pipeline in local mode, Redis state transitions | Real Redis (docker-compose), mocked LLM APIs | 2-3 |
| **Contract** | Provider implementations return valid schemas | Real API call (1 per provider), validate against Protocol | 1 per provider |

### 11.2 Mock Provider

```python
# tests/conftest.py

class MockReasoningProvider:
    name = "mock"

    async def generate_text(self, prompt: str, schema=None) -> str:
        """Return canned JSON matching the expected schema."""
        if "analyze" in prompt:
            return SAMPLE_S1_PATTERN_JSON
        if "generate" in prompt:
            return SAMPLE_SCRIPT_JSON
        ...

    async def analyze_content(self, content: str, prompt: str) -> str:
        return self.generate_text(prompt)
```

### 11.3 What To Test

| Stage | Key Assertions |
|-------|---------------|
| S1 | Output has all required fields. hook_type is one of the valid enum values. |
| S2 | Patterns are deduplicated. Sorted by frequency. Empty input returns empty library. |
| S3 | Returns exactly 50 scripts. Each has non-empty hook, body, payoff. |
| S4 | Returns exactly 5 script IDs. All IDs exist in the candidate list. |
| S5 | Returns exactly 10 ranked scripts. Rank 1 has highest score. |
| S6 | Personalized script differs from original. Video prompt is non-empty. |
| Orchestrator | State transitions fire correctly. Counters reach threshold. Failure handling works. |
| Rate limiter | Respects token count. Blocks when empty. Resets after window. |

---

## 12. Configuration

```python
# app/config.py

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # App
    app_name: str = "flair2"
    debug: bool = False
    environment: str = "dev"                    # dev | staging | prod

    # Redis
    redis_url: str = "redis://localhost:6379"

    # AWS
    aws_region: str = "us-east-1"
    s3_bucket: str = "flair2-pipeline"
    dynamodb_runs_table: str = "pipeline_runs"
    dynamodb_perf_table: str = "video_performance"

    # LLM API Keys
    gemini_api_key: str = ""
    kimi_api_key: str = ""
    openai_api_key: str = ""

    # Video API Keys
    seedance_api_key: str = ""
    veo_api_key: str = ""

    # Rate Limits (requests per minute)
    gemini_rpm: int = 60
    kimi_rpm: int = 60
    openai_rpm: int = 60

    # Pipeline Defaults
    s1_video_count: int = 100
    s3_script_count: int = 50
    s4_persona_count: int = 100
    s6_top_n: int = 10

    # Celery
    celery_broker_url: str = "redis://localhost:6379/1"

    model_config = {"env_file": ".env", "env_prefix": "FLAIR2_"}
```

---

## 13. Dependencies

```toml
# pyproject.toml (key dependencies)

[project]
name = "flair2"
requires-python = ">=3.11"

dependencies = [
    # Web framework
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "sse-starlette>=1.8",           # SSE support for FastAPI

    # Data validation
    "pydantic>=2.6",
    "pydantic-settings>=2.1",

    # Task queue
    "celery[redis]>=5.3",

    # AWS
    "boto3>=1.34",

    # Redis
    "redis>=5.0",

    # LLM Providers
    "google-genai>=0.4",            # Gemini
    "openai>=1.12",                 # OpenAI
    "httpx>=0.27",                  # Kimi (HTTP client), general async HTTP

    # Utilities
    "structlog>=24.1",              # Structured logging
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.1",
    "ruff>=0.3",
    "fakeredis>=2.21",              # In-memory Redis for unit tests
]
```

---

## 14. DDIA Principles Applied

| DDIA Concept | Where Applied | Why |
|---|---|---|
| **Reliability** (Ch. 1) | Typed errors, checkpoint recovery, retry with backoff | Worker crashes don't lose work; LLM failures are retried; infra failures are alerted |
| **Maintainability** (Ch. 1) | 4-layer architecture, pure functions, Pydantic contracts | Any developer can understand a stage by reading its signature. Layers can change independently. |
| **Schema-on-write** (Ch. 2) | Pydantic validation at every stage boundary | Bad LLM output fails immediately, not 3 stages downstream |
| **Encoding evolution** (Ch. 4) | Optional fields with defaults in all models | New fields added without breaking existing data (backward compatible) |
| **Message broker: AMQP model** (Ch. 11) | Celery + Redis BRPOP task queues | Tasks consumed and deleted after processing, not replayed. Work-stealing load balancing. |
| **Checkpointing** (Ch. 11) | Redis checkpoint keys per run per stage | Exactly the stream processing recovery pattern — resume from last committed offset |
| **Idempotency** (Ch. 12) | SETNX cache ensures one LLM call per unique input | Same input re-processed after crash produces same result, no duplicate API costs |
| **Batch processing: MapReduce** (Ch. 10) | S1+S2 (pattern extraction), S4+S5 (crowd voting) | Two full MapReduce cycles with explicit map and reduce phases |
| **Amdahl's Law** | S3 is deliberately sequential | Observable bottleneck for distributed systems course demonstration |
| **CAP: CP** (Ch. 9) | Single-node Redis, single-region DynamoDB | Prefer consistency over availability — stale cache corrupts downstream stages |
| **Rate limiting: Token bucket** | Redis INCR + TTL per provider | Flow control under multi-tenant contention (Experiment 1) |
| **Atomicity: SETNX** (Ch. 7) | Cross-user LLM result cache | Exactly one computation per unique input regardless of concurrency (Experiment 3) |

---

## References

- Spec: `design/spec_v3.md` (v3.2)
- Dataset research: `design/dataset-research.md`
- Psychology research: `design/research/` (8 documents, 4,943 lines)
- Knowledge base: `design/research/` (6 documents, 3,493 lines)
- DDIA: Kleppmann, *Designing Data-Intensive Applications* (2017)
