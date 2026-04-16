# 4. The API Layer

> The API layer's job is to say "yes" fast and get out of the way. If your HTTP handler is doing real work, your architecture is wrong.

## The mental model

Think of the API layer as a receptionist. A receptionist doesn't perform surgery — they check your appointment, hand you a form, and point you to the waiting room. Then they're free to handle the next person. If the receptionist tried to perform surgery on each patient before accepting the next one, the lobby would fill up and nobody would be seen.

Flair2's API layer works the same way. `POST /api/pipeline/start` doesn't run the pipeline — it writes a few Redis keys, enqueues a Celery task, and returns a `run_id`. Milliseconds. The heavy work (LLM calls, pattern analysis, voting) happens elsewhere, on different machines, potentially minutes later.

This pattern has a name: **non-blocking request handling**. Learn to spot it everywhere — it's the foundation of any system that does slow work.

## FastAPI and the app entry point

**File:** `backend/app/main.py`

```python
app = FastAPI(
    title="Flair2 — AI Campaign Studio",
    version="0.1.0",
    lifespan=lifespan,
)
```

The `lifespan` context manager handles startup and shutdown. On shutdown, it closes the Redis connection pool (`await close_redis()`). This is important: without explicit cleanup, the process would leave orphaned TCP connections to Redis.

**CORS configuration** takes up a surprising amount of `main.py`. In development, Astro's dev server runs on port 4321 (or 4322, 4323... if that port is taken — Astro auto-increments). The CORS middleware allows requests from these dev ports. In production, same-origin means no CORS is needed.

**Router registration** is at the bottom — each route module is its own file:
- `health.py` — `GET /api/health` (for ALB health checks)
- `pipeline.py` — start, status (SSE), results
- `providers.py` — list available providers
- `video.py` — video generation endpoints
- `performance.py` — feedback submission

## Dependency injection with `Depends()`

**File:** `backend/app/api/deps.py`

FastAPI's `Depends()` is a lightweight dependency injection system. Instead of creating a Redis connection in every route handler, you declare what you need:

```python
async def start_pipeline(
    req: StartPipelineRequest,
    r: aioredis.Redis = Depends(get_redis),
    session_id: str = Depends(get_session_id),
) -> StartPipelineResponse:
```

When FastAPI sees `Depends(get_redis)`, it calls `get_redis()` before your handler runs and passes the result as the `r` parameter.

### The Redis pool singleton

```python
_redis_pool: aioredis.Redis | None = None

async def get_redis() -> AsyncGenerator[aioredis.Redis, None]:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = aioredis.from_url(
            settings.redis_url,
            decode_responses=True,
        )
    yield _redis_pool
```

This is a **singleton pattern**: the first call creates the pool, subsequent calls reuse it. The `yield` (not `return`) makes this a generator — FastAPI can run cleanup code after the request if needed.

**Why a singleton?** Each `aioredis.from_url()` creates a connection pool (a set of TCP connections to Redis). You want one pool shared across all requests, not a new pool per request. Creating a TCP connection involves a three-way handshake, authentication, and database selection — too slow to do per-request.

**What's missing here:** the pool is created with default settings, including a default `max_connections` (typically 10-50 depending on the library version). Under high concurrency (K=500 in the M5-4 experiment), this default is too small. This is the connection pool bottleneck discussed in [Article 19](19-connection-pool-bottleneck.md).

### Session ID

```python
def get_session_id(session_id: str | None = None) -> str:
    return session_id or "anonymous"
```

Sessions are identified by a query parameter. In production, this would come from a cookie or auth token. For a prototype, "anonymous" as a default is fine. The session ID is used to scope runs — `session:{session_id}:runs` is a Redis list of run IDs belonging to that session.

## The pipeline routes

**File:** `backend/app/api/routes/pipeline.py`

### Starting a run: `POST /api/pipeline/start`

This is the most important endpoint. Let's read it carefully:

```python
@router.post("/api/pipeline/start")
async def start_pipeline(
    req: StartPipelineRequest,
    r: aioredis.Redis = Depends(get_redis),
    session_id: str = Depends(get_session_id),
) -> StartPipelineResponse:
    run_id = str(uuid.uuid4())

    config = PipelineConfig(
        run_id=run_id,
        session_id=session_id,
        reasoning_model=req.reasoning_model,
        # ... other fields
    )

    videos = load_videos_from_json(dataset_path, limit=req.num_videos)
    config.num_videos = len(videos)

    redis_client = RedisClient(settings.redis_url)
    try:
        orchestrator = Orchestrator(redis_client)
        await orchestrator.start(run_id, config, videos)
    finally:
        await redis_client.aclose()

    await r.rpush(f"session:{session_id}:runs", run_id)
    return StartPipelineResponse(run_id=run_id)
```

What happens here, step by step:

1. **Generate a UUID** — every run gets a unique ID. UUIDs are good for this because they're unique without coordination (no database sequence needed).

2. **Build PipelineConfig** — this Pydantic model becomes the single source of truth for the entire run. It's serialized to JSON and stored in Redis at `run:{id}:config`. Workers read it to know what to do.

3. **Load the video dataset** — from a JSON file on disk. This is the file that was infamously excluded from Docker images across PRs #102, #109, #125, #126.

4. **Call `orchestrator.start()`** — this writes state to Redis and dispatches the first batch of Celery tasks (one per video for S1). Covered in detail in [Article 10](10-the-orchestrator.md).

5. **Track the run in the session** — `rpush` adds the run_id to the session's list.

6. **Return `{run_id}`** — the browser now has a handle to poll/stream the run's progress.

**Notice what's NOT here:** there's no `await run_the_pipeline(...)`. The handler returns *immediately* after dispatching tasks. The pipeline runs asynchronously on workers. This is the non-blocking pattern.

**Design pattern — Command/Query Separation:** `POST /api/pipeline/start` is a command (do something). It returns a handle (`run_id`) but not the result. `GET /api/pipeline/status/{run_id}` and `GET /api/pipeline/results/{run_id}` are queries (read something). Commands and queries use different endpoints, different HTTP methods, different response shapes. This separation makes the API predictable.

### Streaming progress: `GET /api/pipeline/status/{run_id}` (SSE)

```python
@router.get("/api/pipeline/status/{run_id}")
async def pipeline_status(
    run_id: str,
    request: Request,
    r: aioredis.Redis = Depends(get_redis),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
) -> EventSourceResponse:
    status = await r.get(f"run:{run_id}:status")
    if status is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    cursor = last_event_id or "0-0"
    return EventSourceResponse(
        sse_event_generator(r, run_id, cursor, request),
    )
```

This endpoint returns a `EventSourceResponse` — an SSE stream. The browser opens this as an `EventSource` and receives events as they're published. The heavy lifting is in `sse_event_generator`, covered in [Article 5](05-sse-and-redis-streams.md).

**The `Last-Event-ID` header:** when an SSE connection drops and the browser reconnects, it sends this header automatically. The server uses it to resume from where the client left off. This is free reconnection — the browser and server cooperate to not lose events, with zero application-level code.

### Getting results: `GET /api/pipeline/results/{run_id}`

```python
if status != PipelineStatus.COMPLETED:
    raise HTTPException(
        status_code=409,
        detail=f"Run {run_id} is {status}, not completed",
    )
```

Returns a `409 Conflict` if the run isn't done yet. This is a good use of HTTP status codes — `409` means "the request is valid but the resource isn't in the right state for this operation." The frontend should check the pipeline status before requesting results.

### Listing runs: `GET /api/runs`

```python
run_ids = await r.lrange(f"session:{session_id}:runs", 0, -1)
```

Reads all run IDs for the current session from Redis and returns their statuses. This is a simple read — no pagination, no filtering. For a prototype, fine. For production with thousands of runs per session, you'd need cursor-based pagination.

## Request validation with Pydantic

**File:** `backend/app/models/api.py`

```python
class StartPipelineRequest(BaseModel):
    creator_profile: CreatorProfile
    reasoning_model: str        # "kimi" | "gemini" | "openai"
    video_model: str | None = None
    num_videos: int = 100
    num_scripts: int = 50
    num_personas: int = 100
    top_n: int = 10
```

FastAPI automatically validates incoming JSON against this Pydantic model. If the request body is missing `creator_profile` or has `num_videos: "banana"`, FastAPI returns a 422 with a detailed error message before your handler even runs.

**Why this matters:** validation at the boundary means the rest of the codebase can assume inputs are valid. No defensive checks scattered throughout stage functions. The API layer is the gatekeeper — once data passes through, it's clean.

## The error hierarchy

**File:** `backend/app/models/errors.py`

```
PipelineError (base)
├── ProviderError      — LLM API failure (retryable)
│   ├── RateLimitError — rate limit hit (backoff + retry)
│   └── InvalidResponseError — unparseable LLM output (retry with stricter prompt)
├── StageError         — pipeline logic failure (halt the stage)
└── InfraError         — Redis/S3/DynamoDB failure (alert + retry)
```

This hierarchy lets catch blocks be precise. A worker can catch `RateLimitError` and back off, catch `InvalidResponseError` and retry, or let `StageError` propagate up to mark the run as failed. Different errors get different responses — that's the point of a hierarchy.

**Design principle:** errors are part of your API. If your code has one generic `Exception` type, every caller has to guess what went wrong. If your errors form a hierarchy, callers can handle each case appropriately.

## What you should notice

1. **The API layer has no business logic.** It validates, enqueues, streams, and returns. The receptionist pattern.

2. **Dependency injection makes testing possible.** In tests, you can replace `get_redis` with a fake Redis, and the route handler doesn't know the difference.

3. **Pydantic does double duty.** It validates incoming requests AND defines the internal data shapes used throughout the pipeline. One model system, two jobs.

4. **HTTP status codes are meaningful.** 404 for missing runs, 409 for incomplete runs, 422 for invalid requests. Each tells the client something specific.

5. **The handler creates a NEW `RedisClient` for the orchestrator** (separate from the injected `r`), then closes it in a `finally` block. This is because the orchestrator needs a `RedisClient` (the application's wrapper class), while the dependency-injected `r` is a raw `aioredis.Redis` connection from the pool. Two different abstractions for two different purposes.

---

***Next: [SSE and Redis Streams](05-sse-and-redis-streams.md) — how the browser stays in sync with the backend, why Streams beat pub/sub, and what makes reconnection free.***
