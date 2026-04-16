# 17. Redis as the Nervous System

> Redis plays five distinct roles in Flair2. This article maps every Redis key pattern, explains what each role does, and discusses why consolidating five roles into one server is both a strength and a vulnerability.

## The five roles

| Role | Redis feature used | Key pattern | Database |
|------|-------------------|-------------|----------|
| **1. Celery broker** | Lists (LPUSH/BLPOP) | `celery`, `_kombu.*` | db=1 |
| **2. Pipeline state** | Strings (SET/GET) | `run:{id}:*` | db=0 |
| **3. SSE event stream** | Streams (XADD/XREAD) | `sse:{id}` | db=0 |
| **4. Rate limiter** | Strings (INCR/EXPIRE) | `ratelimit:{provider}` | db=0 |
| **5. Idempotency cache** | Strings (SETNX) | `s1_result:{id}:{vid}`, etc. | db=0 |

One `cache.t3.micro` ElastiCache instance. Two databases (namespaces). Five jobs. Let's walk through each.

## Role 1: Celery message broker (db=1)

**How Celery uses Redis:** when a producer calls `s1_analyze_task.delay(run_id, video_json)`, Celery serializes the task and pushes it onto a Redis list named `celery`. Workers run `BLPOP celery` — a blocking pop that waits until a message appears.

**Key patterns (managed by Celery, not application code):**
- `celery` — the main task queue (a Redis list)
- `_kombu.binding.*` — Celery's internal routing metadata
- `celery-task-meta-{task_id}` — task results (if `result_backend` is configured)
- `unacked_*` — messages that have been delivered but not acknowledged

**Why db=1:** separation from application data. Celery's internal keys use generic names (`celery`, `_kombu.binding.*`) that could collide with application keys. Using a separate database eliminates the risk.

## Role 2: Pipeline state store (db=0)

This is the canonical state of a pipeline run. Every component reads from here.

**Key patterns:**

```
run:{run_id}:config    → PipelineConfig JSON     (full config, single source of truth)
run:{run_id}:status    → "running" | "completed" | "failed"
run:{run_id}:stage     → "S1_MAP" | "S2_REDUCE" | ... | "DONE" | "FAILED"
run:{run_id}:s1:done   → integer (completion counter for S1 fan-out)
run:{run_id}:s4:done   → integer (completion counter for S4 fan-out)
run:{run_id}:s6:done   → integer (completion counter for S6 fan-out)

session:{session_id}:runs → list of run_ids (Redis list)
```

**Who writes:**
- `run:{id}:config` — written once by the orchestrator at `start()`
- `run:{id}:status` and `run:{id}:stage` — written only by the orchestrator (single writer)
- `run:{id}:s*:done` — incremented by workers via `INCR` (atomic)
- `session:{id}:runs` — appended by the API handler via `RPUSH`

**Who reads:**
- Workers read `run:{id}:config` to know what to do
- API handlers read `run:{id}:status` to check run state
- SSE manager checks `run:{id}:status` to verify run existence
- Orchestrator reads `run:{id}:s*:done` to decide transitions

**TTL:** set to 24 hours after a run reaches terminal state (completed or failed). After 24 hours, all run keys expire automatically. This is garbage collection — without TTLs, Redis would accumulate state from every run forever.

## Role 3: SSE event stream (db=0)

**Key pattern:** `sse:{run_id}` — one Redis Stream per run.

**How it works:** the orchestrator calls `XADD sse:{run_id} * event <type> data <json>` to append events. The SSE manager calls `XREAD {sse:{run_id}: cursor} BLOCK 5000` to read new events with a blocking wait.

**What's in the stream:** every event the pipeline publishes — `pipeline_started`, `stage_started`, `s1_progress`, `vote_cast`, `pipeline_completed`, etc. Each entry is a dict with at least `event` (type) and `data` (JSON payload).

**Why Streams, not pub/sub:** covered in [Article 5](05-sse-and-redis-streams.md). Short version: Streams persist, support cursors (for reconnection), and support multiple independent consumers (for multi-tab).

**Why Streams, not a list:** Lists (LPUSH/BRPOP) are consumed destructively — once a message is popped, it's gone. Streams entries persist until trimmed. Multiple consumers can each maintain their own cursor without interfering with each other.

## Role 4: Rate limiter (db=0)

**Key pattern:** `ratelimit:{provider}` — one counter per provider.

**How it works:** `INCR ratelimit:kimi` increments the counter. If it's the first call in the window, `EXPIRE ratelimit:kimi 60` sets a 60-second TTL. When the key expires, the counter resets. Covered in detail in [Article 16](16-rate-limiting.md).

**Shared across all workers:** this is the whole point. All workers `INCR` the same key, so the counter reflects the global call rate. One Redis key, accurate across any number of workers.

## Role 5: Idempotency cache / result store (db=0)

**Key patterns:**

```
s1_result:{run_id}:{video_id}   → S1Pattern JSON
scripts:{run_id}                → list of CandidateScript JSON
s4_vote:{run_id}:{persona_id}  → PersonaVote JSON
top_scripts:{run_id}            → S5Rankings JSON
s6_result:{run_id}:{script_id} → FinalResult JSON
results:final:{run_id}          → S6Output JSON (the final deliverable)

checkpoint:{run_id}:s4          → integer (checkpoint for crash recovery)
```

These keys serve two purposes:

**1. Intermediate storage between stages.** S1 results must be available for S2. S3 scripts must be available for S4. S5 rankings must be available for S6. Redis is the shared filesystem — each stage writes its output, the next stage reads it.

**2. Idempotency.** If a task runs twice (due to `acks_late` redelivery), the second execution overwrites the same key with the same (or equivalent) result. For the SETNX-based cache pattern, the second execution finds the key already exists and skips the computation entirely. Covered in [Article 18](18-setnx-and-idempotency.md).

## The complete data model

Here is every Redis key the application uses, with lifetime and access pattern:

```
db=0 (application state):
├── Pipeline Run
│   ├── run:{id}:config          W: orchestrator.start()      R: tasks, orchestrator    TTL: 24h after terminal
│   ├── run:{id}:status          W: orchestrator only          R: API, SSE manager       TTL: 24h
│   ├── run:{id}:stage           W: orchestrator only          R: API                    TTL: 24h
│   ├── run:{id}:s1:done         W: INCR by S1 tasks           R: orchestrator           TTL: 24h
│   ├── run:{id}:s4:done         W: INCR by S4 tasks           R: orchestrator           TTL: 24h
│   └── run:{id}:s6:done         W: INCR by S6 tasks           R: orchestrator           TTL: 24h
├── Stage Results
│   ├── s1_result:{id}:{vid}     W: S1 task                    R: S2 task                TTL: 24h
│   ├── scripts:{id}             W: S3 task                    R: S4 tasks, S5 task      TTL: 24h
│   ├── s4_vote:{id}:{persona}   W: S4 task                    R: S5 task                TTL: 24h
│   ├── top_scripts:{id}         W: S5 task                    R: S6 tasks, finalize     TTL: 24h
│   ├── s6_result:{id}:{script}  W: S6 task                    R: finalize               TTL: 24h
│   └── results:final:{id}       W: orchestrator._finalize()   R: API results endpoint   TTL: 24h
├── Infrastructure
│   ├── ratelimit:{provider}     W: INCR by tasks              R: rate_limiter.acquire   TTL: window_seconds
│   ├── checkpoint:{id}:s4       W: orchestrator.on_s4_done    R: orchestrator.recover   TTL: 24h
│   └── session:{sid}:runs       W: RPUSH by API               R: API list_runs          TTL: none
├── SSE Streams
│   └── sse:{id}                 W: XADD by orchestrator       R: XREAD by SSE manager   TTL: 24h
│
db=1 (Celery broker):
├── celery                       W: LPUSH by producers          R: BLPOP by workers       Managed by Celery
├── _kombu.binding.*             W: Celery internal             R: Celery internal
├── celery-task-meta-{tid}       W: Celery on task complete     R: Celery (result backend)
└── unacked_*                    W: Celery                      R: Celery
```

## Why one server works (for now)

**Simplicity:** one ElastiCache instance, one connection URL, one thing to monitor. The operations team (Sam and Jess) doesn't need to manage five different stores.

**Redis is fast:** single-threaded, in-memory, sub-millisecond for simple operations. For Flair2's workload (~261 tasks per run, each making 3-5 Redis calls), a single `cache.t3.micro` handles it easily at low concurrency.

**Logical separation via databases and key namespaces:** db=0 vs db=1 separates Celery from application state. Key prefixes (`run:`, `sse:`, `ratelimit:`, `s1_result:`) prevent naming collisions within db=0.

## Why one server is dangerous (at scale)

**Single point of failure:** if Redis goes down, all five roles fail simultaneously. The queue stops, state is inaccessible, SSE streams break, the rate limiter locks up, and cached results are lost.

**Resource contention:** all five roles share the same CPU, memory, and network bandwidth. A burst of XREAD blocking calls (from many SSE connections) competes with INCR calls (from the rate limiter) and BLPOP calls (from Celery workers). At K=500 in the M5-4 experiment, this contention manifested as connection pool exhaustion.

**Memory pressure:** Redis Streams consume memory for stored entries. Cached LLM results (potentially large JSON) consume memory. Rate limiter keys are tiny. If a burst of concurrent runs fills memory with Stream entries and cache data, Redis might start evicting keys — potentially evicting rate limiter keys or run state.

## How to split (when you need to)

If Flair2 grew to production scale, you'd split Redis roles across separate instances:

1. **Celery broker → separate Redis instance or RabbitMQ.** The broker needs reliability (message durability, redelivery) more than speed. RabbitMQ is purpose-built for this.

2. **SSE Streams → separate Redis instance or Kafka.** Streams can grow large (every event persisted for 24 hours). Isolating them prevents memory pressure on the state store.

3. **Rate limiter → stays on main Redis.** Tiny footprint, needs low latency, fine to share.

4. **State store + cache → main Redis.** These are naturally co-located (tasks read state and write cache in the same call).

**The split order matters:** split the broker first (it's the most operationally critical), then streams (they consume the most memory), then everything else only if measurements show a problem.

## What you should take from this

1. **Map every key pattern before operating a Redis-backed system.** Know what's being stored, who writes it, who reads it, and when it expires. This data model IS the architecture.

2. **Database separation (db=0 vs db=1) prevents naming collisions, not performance isolation.** Both databases share the same Redis process. If you need performance isolation, use separate instances.

3. **TTLs are garbage collection.** Without them, Redis accumulates state forever. Set TTLs on everything that has a natural lifetime.

4. **One server wearing many hats is great for prototypes, dangerous for production.** The convenience of one dependency becomes a liability when that dependency is overloaded or crashes.

5. **Know the split order.** When you outgrow one Redis, don't split everything at once. Identify which role is causing problems (memory? CPU? connection count?) and split that one.

---

***Next: [SETNX and Idempotency](18-setnx-and-idempotency.md) — the cache stampede prevention pattern, and how it saved 90% of LLM calls at K=10.***
