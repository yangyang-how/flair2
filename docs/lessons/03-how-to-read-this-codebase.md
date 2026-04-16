# 3. How to Read This Codebase

> The first thing a senior engineer does with a new repo is build a mental map: what's where, what depends on what, and where to start reading. This article gives you that map.

## The top-level layout

```
flair2/
├── backend/                 # Python backend — the heart of the system
│   ├── app/                 # Application code
│   │   ├── api/             # HTTP layer (FastAPI routes + dependencies)
│   │   ├── infra/           # Infrastructure clients (Redis, DynamoDB, S3)
│   │   ├── models/          # Pydantic data models (shared vocabulary)
│   │   ├── pipeline/        # Pipeline logic (orchestrator + stages + prompts)
│   │   ├── providers/       # LLM provider abstraction (Kimi, Gemini)
│   │   ├── runner/          # CLI + local runner (dev-mode pipeline)
│   │   ├── sse/             # SSE streaming manager
│   │   ├── workers/         # Celery app + task definitions
│   │   ├── config.py        # Pydantic settings (env vars → typed config)
│   │   └── main.py          # FastAPI app entry point
│   └── tests/               # pytest tests
│       ├── unit/            # Fast, no external dependencies
│       ├── integration/     # Needs Redis (real or fake)
│       └── experiments/     # M5/M6 experiment test suites
├── frontend/                # Astro + React frontend
│   └── src/
│       ├── components/      # React islands (interactive parts)
│       ├── layouts/         # Page layouts
│       ├── lib/             # Shared utilities
│       ├── pages/           # Astro pages (routes)
│       └── styles/          # CSS + Tailwind
├── terraform/               # AWS infrastructure as code
│   ├── main.tf              # Root module (VPC, subnets, gateways)
│   └── modules/             # One module per AWS service
│       ├── alb/             # Application Load Balancer
│       ├── dynamodb/        # DynamoDB tables (dormant)
│       ├── ecr/             # Container registry
│       ├── ecs/             # ECS Fargate (API + Worker services)
│       ├── elasticache/     # Redis
│       ├── frontend/        # S3 static website hosting
│       ├── iam/             # IAM roles and policies
│       ├── lambda/          # Lambda function (dormant)
│       └── s3/              # S3 data bucket (dormant)
├── design/                  # Architecture docs, research, specs
├── docs/                    # Reports, homework, lessons
├── data/                    # Video dataset (sample_videos.json)
├── .github/workflows/       # CI/CD pipelines
├── Dockerfile               # Production Docker image
└── ROADMAP.md               # Project plan and milestone tracking
```

## The dependency graph

Understanding what depends on what tells you what's safe to change and what will break everything:

```
main.py
  └── api/routes/*.py          (HTTP handlers)
        ├── api/deps.py         (Redis pool, session ID)
        ├── models/api.py       (request/response shapes)
        ├── pipeline/orchestrator.py  (state machine)
        ├── sse/manager.py      (event streaming)
        └── runner/data_loader.py     (dataset loading)

pipeline/orchestrator.py
  ├── infra/redis_client.py    (all Redis operations)
  ├── models/pipeline.py       (PipelineConfig, PipelineStatus)
  ├── models/stages.py         (stage input/output types)
  └── workers/tasks.py         (dispatches Celery tasks)

workers/tasks.py
  ├── pipeline/stages/s1-s6.py  (pure stage functions)
  ├── providers/registry.py    (provider lookup)
  ├── infra/rate_limiter.py    (token bucket)
  ├── infra/redis_client.py    (state read/write)
  └── pipeline/orchestrator.py  (completion callbacks)

providers/registry.py
  ├── providers/kimi.py        (Kimi via OpenAI SDK)
  └── providers/gemini.py      (Gemini — dormant)
```

**Notice the shape:** it's a tree, not a web. Routes depend on the orchestrator, the orchestrator depends on tasks, tasks depend on stages and providers. Information flows down. This is deliberate — circular dependencies are the enemy of understandable code.

**The one exception:** `workers/tasks.py` and `pipeline/orchestrator.py` depend on each other. The orchestrator dispatches tasks (`s1_analyze_task.delay()`), and tasks call back into the orchestrator (`orchestrator.on_s1_complete()`). This circular dependency is managed with lazy imports (`from app.workers.tasks import s1_analyze_task` inside a method, not at the top of the file). This is a pragmatic choice — the orchestrator and the tasks are conceptually one unit, split into two files for clarity.

## Module boundaries — what each module is responsible for

### `api/` — the HTTP surface

**Owns:** route definitions, request validation, response formatting, dependency injection.
**Does NOT own:** business logic. Routes call the orchestrator or read Redis; they don't run pipeline stages themselves.

The rule: if you're adding a new endpoint, you only touch files in `api/`. If you find yourself importing stage functions into a route handler, something is wrong.

### `pipeline/` — the domain logic

**Owns:** the orchestrator state machine, the six stage functions, the prompt templates.
**Does NOT own:** HTTP concerns, Celery details, Redis connection management.

The stage functions (`s1_analyze`, `s2_aggregate`, etc.) are **pure functions** — they take inputs and a provider, return outputs, and have no side effects. They don't know about Redis, Celery, or HTTP. This is the most important design discipline in the codebase: stage logic is testable without infrastructure.

### `workers/` — the Celery glue

**Owns:** Celery app configuration, task definitions (the wrappers that connect Celery to stage functions).
**Does NOT own:** the stage logic itself. Each task is a thin wrapper: deserialize input → get provider → call pure stage function → store result → notify orchestrator.

### `infra/` — infrastructure clients

**Owns:** Redis client, DynamoDB client, S3 client, rate limiter.
**Does NOT own:** business logic. These are reusable clients that the rest of the codebase calls through.

### `providers/` — LLM abstraction

**Owns:** the `ReasoningProvider` protocol, the provider registry, concrete provider implementations (Kimi, Gemini).
**Does NOT own:** anything about pipelines or stages. A provider just generates text.

### `models/` — the shared vocabulary

**Owns:** Pydantic models that define the shape of data flowing through the system.
**Does NOT own:** behavior. Models are data containers with validation, not actors with methods.

The models module is the one thing every other module imports. This is normal — the data shapes are the shared language of the system.

## Where to start reading

If you're new to the codebase, read in this order:

1. **`models/stages.py`** — read the data shapes first. `VideoInput`, `S1Pattern`, `CandidateScript`, `PersonaVote`, `RankedScript`, `FinalResult`. Once you know what flows between stages, the rest makes sense.

2. **`pipeline/stages/s2_aggregate.py` and `s5_rank.py`** — these two stages have NO LLM calls. They're pure Python functions — `s2_aggregate` groups patterns by type, `s5_rank` counts votes with weighted scoring. Easy to understand, and they show you the stage function pattern without the complexity of LLM interaction.

3. **`pipeline/stages/s1_analyze.py`** — your first LLM-calling stage. Notice the pattern: format prompt → call `provider.generate_text()` → parse JSON response → validate with Pydantic model → return. Every LLM-calling stage follows this pattern.

4. **`api/routes/pipeline.py`** — how the HTTP API works. `POST /api/pipeline/start` and `GET /api/pipeline/status/{run_id}` (SSE). Now you see how requests enter the system.

5. **`pipeline/orchestrator.py`** — how stages chain together. `start()` dispatches S1. `on_s1_complete()` counts completions and triggers S2. Follow the chain all the way to `_finalize()`.

6. **`workers/tasks.py`** — how Celery connects everything. The task wrappers that bridge the orchestrator, the stage functions, and the provider.

## Naming conventions

The codebase is consistent about naming. Once you learn the conventions, you can predict where things live:

- **`s1_`, `s2_`, ..., `s6_`** — stage number prefix. `s1_analyze`, `s4_vote`, `s1_analyze_task`.
- **`run:{id}:*`** — Redis key namespace for pipeline run state.
- **`sse:{id}`** — Redis Stream key for SSE events.
- **`ratelimit:{provider}`** — Redis key for rate limiter counters.
- **`checkpoint:{id}:{stage}`** — Redis key for crash recovery checkpoints.
- **`results:final:{id}`** — Redis key for final pipeline output.
- **`*_task`** — Celery task functions (e.g., `s1_analyze_task`).
- **`on_s*_complete`** — orchestrator callbacks (e.g., `on_s1_complete`).
- **`_transition_s*`** — orchestrator stage transitions (e.g., `_transition_s2`).

## How the tests are organized

```
tests/
├── unit/                    # No external deps, fast, runs everywhere
│   ├── test_models.py       # Data model validation
│   ├── test_orchestrator.py # Orchestrator state transitions
│   ├── test_rate_limiter.py # Rate limiter logic
│   ├── test_kimi_provider.py
│   ├── test_api_routes.py
│   └── ...
├── integration/             # Needs Redis (fakeredis or real)
│   └── test_multi_user.py   # K concurrent pipeline runs
└── experiments/             # M5/M6 experiments (some need AWS)
    ├── test_backpressure.py      # M5-1
    ├── test_failure_recovery.py  # M5-2
    ├── test_cache_concurrency.py # M5-3
    ├── test_e2e_pipeline.py      # M5 end-to-end
    ├── test_elasticache_integration.py  # M6
    ├── locustfile.py             # M5-4 load test
    └── run_load_test.sh          # Locust runner script
```

**The testing principle:** unit tests test logic without infrastructure; integration tests test the seams where components meet; experiment tests are science — they answer questions, not just verify behavior.

## One more thing: the interface contract

Many files reference "Contract: #71" in their docstrings. This refers to [GitHub issue #71](https://github.com/yangyang-how/flair2/issues/71), which defines the interface contract between the API, the orchestrator, the workers, and the SSE stream. It specifies:

- Every Redis key pattern and its purpose
- Every SSE event type and its payload
- The API endpoint signatures
- TTL policies

This is the document that let Sam and Jess work independently. When you see a comment saying "Contract: #71 Section 2," it means "this code implements the SSE event format agreed in the contract." If the code doesn't match the contract, it's a bug — and the contract is the authority, not the code.

**Design principle:** in a multi-person project, the contract is the source of truth for integration points. The code implements the contract; the contract doesn't describe the code.

---

***Next: [The API Layer](04-the-api-layer.md) — how FastAPI handles requests, dependency injection, and why the handler returns in milliseconds.***
