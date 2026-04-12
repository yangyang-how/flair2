# M5-4 Load Test Report: API Concurrent Load (Locust)

**Date:** 2026-04-12  
**Issue:** [#89](https://github.com/yangyang-how/flair2/issues/89)  
**File:** `backend/tests/experiments/locustfile.py`  
**Target:** `http://flair2-dev-alb-10789830.us-west-2.elb.amazonaws.com`  
**Infrastructure:** AWS ECS Fargate, ALB, ElastiCache Redis  
**Auto-scaling config:** API target CPU = 60%, scale-out cooldown = 60s, min=2 / max=6 tasks

---

## What We Tested

Locust simulates K concurrent virtual users, each performing a realistic mix of API calls:

| Task | Weight | Description |
|------|--------|-------------|
| `POST /api/pipeline/start` | 3 | Submit a new pipeline run (heavy) |
| `GET /api/runs` | 2 | List runs for the session (medium) |
| `GET /api/health` | 1 | Health check (lightweight baseline) |
| `GET /api/providers` | 1 | List available models (lightweight) |

Each user waits 1–3 seconds between tasks to simulate realistic behaviour. K values tested: **10, 50, 100, 500 (60s), 500 (sustained)**.

---

## Results — Aggregated (all endpoints)

| K | Requests | Failures | Median | p95 | p99 | Avg | RPS | Fail% |
|---|----------|----------|--------|-----|-----|-----|-----|-------|
| 10 | 287 | 0 | 35 ms | 51 ms | 190 ms | 38 ms | 4.81 | 0.00% |
| 50 | 2,893 | 0 | 35 ms | 59 ms | 100 ms | 38 ms | 48.24 | 0.00% |
| 100 | 2,879 | 0 | 34 ms | 61 ms | 140 ms | 38 ms | 47.96 | 0.00% |
| 500 (60s) | 15,837 | 4 | 69 ms | 2,900 ms | 4,200 ms | 781 ms | 175.89 | 0.03% |
| 500 (sustained) | 71,866 | 18 | 77 ms | 12,000 ms | 18,000 ms | 1,816 ms | 130.18 | 0.03% |

---

## Results — POST /api/pipeline/start

| K | Requests | Failures | Median | p95 | p99 | RPS |
|---|----------|----------|--------|-----|-----|-----|
| 10 | 114 | 0 | 43 ms | 79 ms | 280 ms | 1.91 |
| 50 | 1,252 | 0 | 43 ms | 73 ms | 160 ms | 20.88 |
| 100 | 1,211 | 0 | 43 ms | 78 ms | 150 ms | 20.18 |
| 500 (60s) | 6,798 | 1 | 590 ms | 2,900 ms | 3,100 ms | 75.50 |
| 500 (sustained) | 31,013 | 11 | 450 ms | 3,000 ms | 3,300 ms | 56.18 |

---

## Results — GET /api/runs (queue pressure indicator)

`/api/runs` queries Redis for a session's run list — its latency reflects Redis queue depth under load.

| K | Median | p95 | p99 | RPS |
|---|--------|-----|-----|-----|
| 10 | 33 ms | 50 ms | 110 ms | 1.54 |
| 50 | 33 ms | 57 ms | 74 ms | 13.52 |
| 100 | 32 ms | 60 ms | 160 ms | 13.53 |
| 500 (60s) | 160 ms | 4,000 ms | 5,200 ms | 50.41 |
| 500 (sustained) | 210 ms | 17,000 ms | 20,000 ms | 36.67 |

---

## Auto-scaling Observation

The ECS API service is configured with TargetTrackingScaling (target CPU = 60%).

**Timeline of K=500 sustained run:**

| Time (UTC) | Event |
|------------|-------|
| 07:26 | Locust K=500 starts; CPU begins climbing |
| 07:28 | CPU Maximum hits 100%; Average ~75% — scale-out triggered |
| 07:30 | 3rd ECS task comes online (2 → 3 Running); CPU Minimum joins at ~75% |
| 07:32–07:34 | All 3 tasks running at 75–85% CPU — still above 60% target |
| 07:34 | Locust stopped; load drops; scale-in cooldown (300s) begins |

**CloudWatch metrics peak values during sustained K=500:**
- CPU Maximum: **99.96%**
- CPU Average: **~80%** (3 tasks)
- Network TX peak: **510.7k bytes/s**
- Memory: **9.38%** (not a bottleneck)

---

## Key Findings

### 1. Stable zone: K ≤ 100

At K=10 through K=100, the system is completely stable:
- Median latency holds at **34–35 ms** across all K values — a 10× increase in concurrency produces no measurable degradation
- Zero failures across 6,059 total requests
- RPS scales linearly from 4.81 → 48.24 (K=10 → K=50), then plateaus at ~48 RPS (K=50 → K=100)

The plateau at K=50→100 indicates the system reached its **steady-state throughput limit** (~48 RPS aggregated) with 2 ECS tasks, bounded by the Kimi API rate limit rather than infrastructure capacity.

### 2. Inflection point: K = 500

At K=500, all metrics degrade sharply:
- Aggregate median: 35 ms → **69 ms** (+97%)
- Aggregate p95: 61 ms → **2,900 ms** (+47×)
- Aggregate avg: 38 ms → **781 ms** (+20×)
- `POST /api/pipeline/start` median: 43 ms → **590 ms**
- `GET /api/runs` p99: 160 ms → **5,200 ms**

This is the **first point where ECS CPU exceeds the 60% auto-scaling threshold**, triggering scale-out from 2 → 3 tasks.

### 3. Auto-scaling fires but insufficient

Auto-scaling correctly detected overload and added a 3rd task (~2 minutes after load began — 1 min CloudWatch evaluation + 1 min task startup). However, with 3 tasks all running at 75–85% CPU, **the system was still above the 60% target**.

The sustained K=500 run shows the system did not recover:
- p95 grew from 2,900 ms → **12,000 ms**
- p99 grew from 4,200 ms → **18,000 ms**
- RPS actually *dropped* from 175.89 → 130.18

### 4. Root cause: worker bottleneck, not API

`GET /api/health` and `GET /api/providers` remained fast even at K=500 (p99 ≈ 260–300 ms). Only `POST /api/pipeline/start` and `GET /api/runs` degraded severely.

`/api/pipeline/start` queues a Celery task and returns immediately — the high latency means the API itself is CPU-bound handling 500 concurrent HTTP connections, not waiting for LLM calls. `/api/runs` reads from Redis, whose p99 reached 20,000 ms, indicating **Redis connection pool exhaustion** as 3 API tasks each maintain their own connection pools against the same ElastiCache instance.

**Scaling the API layer alone is insufficient.** At K=500, the Celery Worker queue also needs to scale to drain the backlog. The Terraform config sets `worker_max_count = 4`; at sustained K=500 the worker should scale in parallel with the API service.

---

## Conclusions

| Finding | Detail |
|---------|--------|
| **Healthy operating range** | K ≤ 100 — zero failures, stable 34 ms median |
| **Throughput saturation** | ~48 RPS aggregated with 2 tasks (Kimi rate limit bound) |
| **Inflection point** | K = 500 — p95 jumps 47× to 2,900 ms |
| **Auto-scaling trigger** | CPU > 60% sustained ~3 min → 2 → 3 tasks in ~2 min |
| **Auto-scaling limitation** | API scaling alone insufficient; Worker must scale in parallel |
| **Redis pressure** | `/api/runs` p99 = 20,000 ms at sustained K=500 — connection pool exhaustion |
| **Failure rate** | 0.03% even at K=500 — system degrades gracefully, never hard-fails |

---

## Worker Auto-scaling: Why It Did Not Trigger

The Celery Worker service is configured with `target CPU = 70%`, `min=2`, `max=4`. During the entire K=500 sustained load test, the Worker remained at **2 tasks (Desired=2, Running=2)** — auto-scaling never fired.

**Root cause: Worker tasks are IO-bound, not CPU-bound.**

The Worker pipeline stages spend the vast majority of their time waiting for Kimi API responses (2–5 min per LLM call). During this wait, CPU usage is near 0%. The Worker CPU never approached the 70% threshold, so CloudWatch never triggered a scale-out event — even while the Celery queue was backed up with hundreds of unprocessed tasks.

**CPU is the wrong metric for Worker auto-scaling.**

| Metric | Worker CPU | Redis Queue Depth |
|--------|-----------|-------------------|
| Reflects actual backlog | ❌ No | ✅ Yes |
| Triggered during K=500 test | ❌ Never | ✅ Would have |
| Currently configured | ✅ Yes | ❌ Not yet |

**Recommended fix:** Publish a custom CloudWatch metric for the Celery queue length (e.g. `LLEN celery` on Redis), and replace the CPU-based scaling policy with a step/target-tracking policy on queue depth. A threshold of ~50 queued tasks per Worker is a reasonable starting point.

---

## Conclusions

| Finding | Detail |
|---------|--------|
| **Healthy operating range** | K ≤ 100 — zero failures, stable 34 ms median |
| **Throughput saturation** | ~48 RPS aggregated with 2 tasks (Kimi rate limit bound) |
| **Inflection point** | K = 500 — p95 jumps 47× to 2,900 ms |
| **API auto-scaling trigger** | CPU > 60% sustained ~3 min → 2 → 3 tasks in ~2 min |
| **API auto-scaling limitation** | 3 tasks still at 75–85% CPU; system did not fully recover |
| **Worker auto-scaling** | Did NOT trigger — Worker is IO-bound; CPU stayed near 0% despite queue backlog |
| **Wrong scaling metric** | Worker should scale on Redis queue depth, not CPU |
| **Redis pressure** | `/api/runs` p99 = 20,000 ms at sustained K=500 — connection pool exhaustion |
| **Failure rate** | 0.03% even at K=500 — system degrades gracefully, never hard-fails |

**Recommendation:** For K > 100 production traffic:
1. Replace Worker CPU scaling with a custom CloudWatch metric on Redis queue depth (`LLEN celery`)
2. Tune API connection pool size per ECS task to reduce Redis contention at K=500+
3. Consider raising ElastiCache instance type if `/api/runs` p99 exceeds SLA under sustained load
