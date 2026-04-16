# 6. The Request Lifecycle, End to End

> This article ties together Articles 4 and 5 by walking one pipeline run from the user's click to the final result. Every component appears in the order it actually executes.

## The setup

A user has entered a brand name and creator profile into the Astro frontend, selected "Kimi" as the reasoning model, and clicked "Generate." Here is everything that happens next, in order, with file references.

## Phase 1: The request arrives (milliseconds)

### Browser → ALB → API Task

The browser sends:

```http
POST /api/pipeline/start
Content-Type: application/json

{
  "creator_profile": {
    "tone": "casual",
    "vocabulary": ["vibe", "literally"],
    "catchphrases": ["hear me out"],
    "topics_to_avoid": ["politics"],
    "niche": "tech reviews"
  },
  "reasoning_model": "kimi",
  "num_videos": 100,
  "num_scripts": 50,
  "num_personas": 100,
  "top_n": 10
}
```

The ALB health-checks all API tasks and routes this request to a healthy one. FastAPI validates the JSON body against `StartPipelineRequest` (`models/api.py:14`). If validation fails (missing `creator_profile`, wrong types), FastAPI returns 422 immediately — the handler never runs.

### Handler runs (`api/routes/pipeline.py:34`)

1. **UUID generated:** `run_id = str(uuid.uuid4())` — e.g., `"a1b2c3d4-e5f6-..."`. No database needed, no coordination between API tasks. UUIDs are designed to be unique without a central authority.

2. **PipelineConfig built:** all request parameters plus the `run_id` and `session_id` are packed into a `PipelineConfig` Pydantic model. This is the single source of truth for the entire run — workers will read it from Redis.

3. **Dataset loaded:** `load_videos_from_json()` (`runner/data_loader.py`) reads `data/sample_videos.json` and returns up to `num_videos` `VideoInput` objects. This file is baked into the Docker image.

4. **Orchestrator called:** `orchestrator.start(run_id, config, videos)` — this is where the real initialization happens. Covered in Phase 2 below.

5. **Session tracking:** `rpush(f"session:{session_id}:runs", run_id)` adds the run to the session's list.

6. **Response returned:** `{"run_id": "a1b2c3d4-e5f6-..."}`. The browser now has a handle. **Total time: tens of milliseconds.** The pipeline hasn't started running yet.

## Phase 2: Orchestrator initializes state (milliseconds)

**File:** `pipeline/orchestrator.py:37` — `start()`

The orchestrator writes to Redis:

```
run:a1b2c3d4:config     → PipelineConfig JSON (entire config)
run:a1b2c3d4:status     → "running"
run:a1b2c3d4:stage      → "S1_MAP"
run:a1b2c3d4:s1:done    → "0"
run:a1b2c3d4:s4:done    → "0"
run:a1b2c3d4:s6:done    → "0"
```

Then it publishes events to the Redis Stream:

```
XADD sse:a1b2c3d4 * event pipeline_started data {"run_id":"a1b2c3d4","total_videos":100,...}
XADD sse:a1b2c3d4 * event stage_started data {"stage":"S1_MAP","total_items":100}
```

Finally, it dispatches 100 Celery tasks — one per video:

```python
for video in videos:
    s1_analyze_task.delay(run_id, video.model_dump_json())
```

`.delay()` serializes the arguments to JSON and pushes a message onto the Celery queue in Redis (db=1). The orchestrator doesn't wait for any of these tasks to complete. It enqueues them and returns.

**What just happened:** the API task did maybe 10ms of work, wrote ~10 Redis keys, pushed 100 messages onto a queue, and returned. The user has a `run_id`. The real work is about to start on the workers.

## Phase 3: The browser connects for streaming

The browser, having received the `run_id`, opens an SSE connection:

```javascript
const evtSource = new EventSource(`/api/pipeline/status/${runId}`);
```

This hits `GET /api/pipeline/status/a1b2c3d4` on the API task. The handler in `pipeline.py:98` verifies the run exists, then returns an `EventSourceResponse` backed by `sse_event_generator` (`sse/manager.py`).

The SSE generator starts an XREAD loop on `sse:a1b2c3d4` with cursor `"0-0"`. Since the orchestrator already published `pipeline_started` and `stage_started` events in Phase 2, the first XREAD immediately returns those two events. The browser receives them and updates the UI to show "Pipeline started, analyzing 100 videos..."

From this point on, the SSE connection is held open. The API task is a bridge: it blocks on XREAD, relays events to the browser, and repeats.

## Phase 4: S1 — Map (analyze videos) (seconds)

**Workers pop tasks from the queue.**

Each of the 2-4 Celery workers pulls `s1_analyze_task` messages from Redis db=1. Since `worker_prefetch_multiplier=1`, each worker takes only one task at a time.

**For each task** (`workers/tasks.py` — the S1 task):

1. Load `PipelineConfig` from `run:{id}:config` in Redis
2. Resolve the provider: `_get_provider(config)` → `KimiProvider(api_key=...)`
3. Wait for a rate limit token: `TokenBucketRateLimiter.wait_for_token()` — blocks until under the per-minute limit
4. Call the pure stage function: `s1_analyze(video, provider)` — sends a prompt to Kimi, parses the JSON response into an `S1Pattern`
5. Store the result: `redis.set(f"s1_result:{run_id}:{video.video_id}", pattern.model_dump_json())`
6. Notify the orchestrator: `orchestrator.on_s1_complete(run_id, video.video_id)`

**In the orchestrator** (`on_s1_complete`):

```python
done = await self._r.incr(f"run:{run_id}:s1:done")  # atomic increment
```

This is the coordination mechanism. 100 workers might be completing S1 tasks concurrently. `INCR` is atomic in Redis — exactly one of them will see `done == 100` and trigger the transition to S2.

The orchestrator publishes `s1_progress` events to the stream. The SSE manager picks them up. The browser shows: "Analyzed 1/100... 2/100... 42/100..."

When `done >= config.num_videos`, the orchestrator calls `_transition_s2()`.

## Phase 5: S2 — Reduce (aggregate patterns) (sub-second)

**One task, not many.** `_transition_s2` dispatches a single `s2_aggregate_task`.

The worker reads all S1 results from Redis, passes them to `s2_aggregate()` (`pipeline/stages/s2_aggregate.py`). This function is pure Python — no LLM call. It groups patterns by type, counts frequencies, sorts by frequency. Returns an `S2PatternLibrary`.

The result is stored in Redis. The orchestrator publishes `s2_complete`. The SSE stream forwards to the browser.

Transition to S3.

## Phase 6: S3 — Sequential (generate scripts) (seconds)

**One task.** `s3_generate` reads the pattern library and generates candidate scripts. This stage makes multiple sequential LLM calls (one per script, distributed across patterns proportional to frequency).

S3 is deliberately sequential. It's a bottleneck — and that's intentional. The scripts need to be diverse (different patterns, different hooks). Generating them concurrently might produce duplicates because each LLM call wouldn't know what the others generated. Sequential generation lets each call's output inform the next call's context (in principle — the current implementation doesn't do this, but the sequential design leaves room for it).

50 scripts generated. Stored in Redis. `s3_complete` published. Transition to S4.

## Phase 7: S4 — Map (persona voting) (seconds)

**100 tasks dispatched.** One per persona. This is the second fan-out.

Each worker picks up a persona task, reads all 50 candidate scripts from Redis, and asks the LLM: "You are persona_42. Here are 50 scripts. Pick your top 5."

The orchestrator tracks progress with `run:{id}:s4:done`. Each completion also writes a checkpoint (`checkpoint:a1b2c3d4:s4`) — this is for crash recovery, covered in [Article 12](12-checkpoint-and-recovery.md).

The SSE stream sends `vote_cast` events. The browser shows the voting animation — 100 personas casting votes, one by one, with Framer Motion animations.

When all 100 personas have voted, transition to S5.

## Phase 8: S5 — Reduce (rank by votes) (sub-second)

**One task.** Pure Python, no LLM. Reads all persona votes from Redis. Applies weighted scoring: 1st pick = 5 points, 2nd = 4, 3rd = 3, 4th = 2, 5th = 1. Sorts by total score. Returns the top N scripts.

```python
# From s5_rank.py
score_weights = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1}
```

This is a simple vote aggregation — Borda count, essentially. The scores are stored in Redis. `s5_complete` published with the winning script IDs. Transition to S6.

## Phase 9: S6 — Map (personalize top scripts) (seconds)

**N tasks dispatched** (default: 10). Each takes a winning script and rewrites it in the creator's voice, plus generates a video prompt.

The worker reads the creator profile from the config, passes it with the script to `s6_personalize()`. The LLM adapts the script's tone, vocabulary, and catchphrases to match the creator.

Progress events: `s6_progress`. When all N are done, the orchestrator finalizes.

## Phase 10: Finalize

**The orchestrator** (`_finalize`):

1. Reads all S6 results from Redis
2. Attaches rank and vote scores from S5
3. Assembles an `S6Output` with all final results
4. Stores at `results:final:{run_id}` with a 24-hour TTL
5. Sets `run:{id}:status = "completed"`, `run:{id}:stage = "DONE"`
6. Publishes `pipeline_completed` to the SSE stream
7. Sets TTL on all run keys (24-hour expiry)

The SSE manager receives `pipeline_completed`, yields it to the browser, and returns (ending the generator, which closes the SSE connection).

The browser can now call `GET /api/pipeline/results/a1b2c3d4` to get the final results.

## The timeline

```
t=0ms      POST /api/pipeline/start → run_id returned
t=10ms     Browser opens SSE connection
t=50ms     First S1 tasks start on workers
t=2-5s     S1 progress events streaming (100 videos)
t=5s       S2 aggregate (sub-second)
t=5-8s     S3 generate (50 scripts, sequential)
t=8-12s    S4 voting (100 personas, concurrent)
t=12s      S5 rank (sub-second)
t=12-15s   S6 personalize (10 scripts, concurrent)
t=15s      pipeline_completed — SSE closes
```

The actual timing depends on Kimi's response latency and the rate limiter's budget. But the shape is consistent: two fast fan-outs (S1, S4), two fast reductions (S2, S5), one sequential bottleneck (S3), one small fan-out (S6).

## Visualizing the data flow

```
100 videos ──► S1 (map: 100 tasks) ──► 100 patterns
                                              │
                                        S2 (reduce: 1 task)
                                              │
                                        1 pattern library
                                              │
                                        S3 (sequential: 1 task)
                                              │
                                        50 candidate scripts
                                              │
100 personas ──► S4 (map: 100 tasks) ──► 100 persona votes
                                              │
                                        S5 (reduce: 1 task)
                                              │
                                        top 10 ranked scripts
                                              │
                          S6 (map: 10 tasks) ──► 10 personalized results
```

**Two MapReduce cycles:**
- Cycle 1: S1 (map) → S2 (reduce) — discover patterns
- Cycle 2: S4 (map) → S5 (reduce) — evaluate scripts

S3 and S6 are connectors between the cycles. S3 transforms the reduce output into new map input. S6 transforms the final rankings into deliverables.

## What you should notice

1. **The browser never talks to a worker.** The entire request lifecycle goes through the API and Redis. Workers are invisible to the frontend. This is what makes independent scaling possible.

2. **The API task holds two connections.** One to the browser (SSE), one to Redis (XREAD). It's a relay, not a processor.

3. **The orchestrator is the single writer.** All state transitions, all SSE events, all stage dispatches go through the orchestrator. No races, no interleaving.

4. **Fan-out/fan-in is the heartbeat.** Dispatch N tasks, track completion with an atomic counter, trigger the next stage when the counter hits N. This pattern repeats three times (S1, S4, S6).

5. **The total LLM calls are predictable.** `num_videos + num_scripts + num_personas + top_n` = 100 + 50 + 100 + 10 = 260 calls (S2 and S5 are algorithmic, not LLM). This makes rate limiting, cost estimation, and capacity planning possible.

---

***Next: [What Celery Is (and Isn't)](07-what-celery-is.md) — the mental model for task queues, and why they exist.***
