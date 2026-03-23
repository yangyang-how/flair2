# Architecture — AI Campaign Studio V2

## Architecture Decisions

This is a two-service architecture designed for three audiences: the distributed systems course, a resume for agentic engineering roles, and actual usability during development.

### Frontend (Cloudflare Pages)
Astro + React islands. Astro handles the static shell — forms, layout, campaign display. React islands hydrate only where we need interactivity: the pipeline stage visualization (long-running animation while the backend processes) and the audience voting animation (100 simulated audience members voting with visual aggregation). This split keeps the bundle small and the deploy instant. Cloudflare Pages gives us auto-deploy on every GitHub merge with preview URLs on every PR — we can test visually within minutes of merging.

### Backend (AWS ECS + Application Load Balancer)
Python/FastAPI with Redis (ElastiCache) for shared state and Celery for the task queue. Deployed on AWS ECS Fargate behind an Application Load Balancer. Multiple API instances run concurrently — the ALB distributes incoming HTTP and SSE connections across them. This is where the distributed systems work lives.

**Why ALB + multiple instances**: A single API instance becomes the bottleneck when 10+ concurrent pipeline runs each hold an open SSE connection while workers process. The ALB enables horizontal scale-out of the API tier without changing any application code. This is the same pattern used in CS6650 HW6.

**Worker-level load balancing**: Celery workers do not need an explicit load balancer. Each worker issues a `BRPOP` against the Redis task queue — whichever worker is free picks the next task. This is work-stealing by design. Adding more workers increases throughput linearly until the LLM API rate limit becomes the ceiling.

### Why This Split
Python backend is the industry standard for AI services — every agentic engineering role expects it. Cloudflare Pages frontend gives us the instant deploy workflow that makes development fast. The two-service architecture itself demonstrates distributed systems thinking: an edge frontend communicating with an API backend, with internal distribution (workers, queues, Redis) inside the backend. This is three layers of distribution visible in one project.

### Frontend ↔ Backend Communication
SSE (Server-Sent Events) for pipeline status updates. The frontend opens an SSE connection when a campaign generation starts, and the backend streams stage completion events. This is better than polling for the visualization — the animation updates in real-time as each pipeline stage completes. For the voting visualization, the backend streams individual vote events so the frontend can animate each one.

On SSE reconnect (network drop), the frontend hits `GET /api/pipeline/status` to fetch current stage, then re-opens the SSE stream. No pipeline state is lost — all state lives in Redis, not in the API process.

---

## Pipeline Stages

```
INPUT: 100 videos from Tsinghua/Kuaishou dataset

┌─ MapReduce Cycle 1 ──────────────────────────────────────────┐
│  S1 MAP     100 videos  →  N workers  →  1 pattern per video │
│  S2 REDUCE  N patterns  →  1 worker   →  pattern library     │
└──────────────────────────────────────────────────────────────┘

S3 SEQUENTIAL  pattern library  →  50 candidate scripts
               (deliberate bottleneck — Amdahl's Law observation)

┌─ MapReduce Cycle 2 ──────────────────────────────────────────┐
│  S4 MAP     100 simulated voters  →  N workers  →  top 5 ea  │
│  S5 REDUCE  votes  →  1 worker    →  ranked top 10 scripts   │
└──────────────────────────────────────────────────────────────┘

S6 STYLE INJECT
   top 10 + creator voice profile  →  10 personalized scripts
```

**Total LLM calls**: ~300 (100 analyze + 50 generate + 100 vote + 10 personalize).  
**Runtime at 10 workers**: ~45 minutes.

---

## Redis Design

Redis (AWS ElastiCache, single node) is the coordination layer for all workers. Workers never communicate directly — all shared state flows through Redis.

### Task Queue (BRPOP / RPUSH)
Each stage uses a Redis list as a task queue. Workers block on `BRPOP` — they sleep until a task is available, then process it and push results to a result key. This is the standard Celery/Redis pattern and provides work-stealing load balancing across workers at no extra cost.

```
task:s1        LIST  — video IDs pending S1 analysis
task:s4        LIST  — persona IDs pending S4 voting
result:s1:{id} STRING — JSON pattern object from S1
result:s4:{id} STRING — JSON list of 5 script IDs
```

### SETNX Cache (Deduplication)
LLM calls are expensive and slow (~1–10s each). If a worker crashes mid-stage and the task is retried, we must not re-call the LLM for work already completed. We also must not allow two workers to compute the same result simultaneously (wasted cost + potential inconsistency).

Solution: before calling the LLM, each worker issues `SETNX cache:{video_id}:{prompt_hash} "computing"`. Only one worker wins the lock. Others see the key exists and wait for the result to appear. This guarantees exactly one LLM call per unique input, regardless of concurrency or retries.

This is the subject of **Experiment 3** — we will measure duplicate LLM calls under naive GET/SET vs SETNX to quantify the cost of not using atomic operations.

### Token Bucket Rate Limiter
The LLM APIs enforce rate limits (e.g., 60 req/min for Kimi). Without control, N=50 workers will simultaneously flood the endpoint and receive 429 errors, causing cascading retries that make the pipeline slower, not faster.

We implement a token bucket in Redis: a counter key with TTL = 1 minute, decremented atomically before each LLM call. Workers that find the bucket empty wait with exponential backoff + jitter before retrying.

This is the subject of **Experiment 1** — we will run S1 with N = 1, 5, 10, 20, 50 workers under two conditions (limiter vs no limiter) and measure error rate and actual throughput.

### Checkpoint (Partial Failure Recovery)
After completing each task, the worker writes `checkpoint:{stage} {last_completed_index}` to Redis. On restart after a crash, the worker reads this key and resumes from the last completed index rather than starting over.

Without checkpointing, a crash at task 75 of 100 wastes 75 LLM calls. With checkpointing, recovery is O(1) — the worker reads one key and skips directly to task 76.

This is the subject of **Experiment 2** — we will simulate crashes at 25%, 50%, and 75% completion and measure API calls saved by checkpoint vs full restart.

### CAP Theorem Position
We use a **single-node Redis (CP)**. In the event of a network partition, Redis will refuse writes rather than return stale data. This is the correct trade-off for our pipeline: a worker reading a wrong cached LLM result would silently corrupt downstream stages (pattern library, script ranking). We prefer the pipeline to stall with an error over producing incorrect output.

If we used Redis Cluster (AP), partitions could return stale checkpoint or cache data, causing workers to re-run completed tasks or overwrite correct results with duplicate computations. We explicitly accept the lower availability of CP for correctness guarantees.

---

## Persistent Storage (DynamoDB)

Redis is ephemeral — pipeline state is lost on restart. Final results (top 10 personalized scripts, video prompts) are written to DynamoDB at the end of S6, keyed by `pipeline_run_id`.

**Access pattern**: always read by `pipeline_run_id`. No joins needed. DynamoDB's single-key access pattern is a natural fit.

**CAP position for DynamoDB**: single-region DynamoDB with default eventual consistency. For results storage, eventual consistency is acceptable — the user reads their results after the pipeline completes, not during. We are not doing concurrent writes to the same run's results.

**Future experiment (optional)**: if we enable DynamoDB Global Tables (multi-primary, AP), we can measure whether eventual consistency affects vote aggregation accuracy in S5 — a concrete demonstration of CAP trade-offs in a real workload.

---

## Distributed Systems Concepts Demonstrated

| Concept | Where | Experiment |
|---------|-------|-----------|
| MapReduce ×2 | S1+S2 (pattern extraction), S4+S5 (voting) | — |
| Work-stealing via BRPOP | All map stages | — |
| Token bucket rate limiting | Before every LLM call | Experiment 1 |
| Checkpoint-based recovery | After every completed task | Experiment 2 |
| SETNX atomic cache | LLM result deduplication | Experiment 3 |
| SSE streaming | Frontend pipeline visualization | — |
| Load balancing (ALB) | API tier horizontal scale-out | — |
| CAP theorem (CP) | Redis single-node design decision | — |
| Amdahl's Law | S3 deliberate sequential bottleneck | — |

---

## V1 → V2 Changes

- Monolithic `main.py` → separated orchestration, integration, and worker modules
- In-memory state → Redis-backed state (ElastiCache) — survives worker restarts
- Sequential pipeline → concurrent workers with MapReduce patterns + BRPOP work-stealing
- Vanilla JS single-page → Astro + React islands with animations
- Google Cloud Run → AWS ECS Fargate + ALB (consistent with CS6650 infrastructure)
- No rate limiting → Token bucket in Redis before every LLM call
- No fault tolerance → Checkpoint after every task, SETNX cache deduplication
- No tests → pytest with unit + integration coverage
- No CI → GitHub Actions on every push

## V2 Gaps to Close

1. **Spec-First Discipline** — design doc before any code
2. **Testing & CI** — pytest on day one, every module has unit tests, 5+ integration tests
3. **CI/CD & Production Hygiene** — lint + test + build on push, reliable Dockerfile, structured logging
4. **Review Muscle** — every PR reviewed, review log maintained
5. **Open Questions** — resolve before writing code (see project spec Section 11)
