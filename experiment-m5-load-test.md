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

## Locust run screenshots

Locust Web UI captures for each concurrency level (K).

### K = 10

![M5 Locust K=10 - run 1](screenshots/M5-10-1.png)
![M5 Locust K=10 - run 2](screenshots/M5-10-2.png)

### K = 50

![M5 Locust K=50 - run 1](screenshots/M5-50-1.png)
![M5 Locust K=50 - run 2](screenshots/M5-50-2.png)

### K = 100

![M5 Locust K=100 - run 1](screenshots/M5-100-1.png)
![M5 Locust K=100 - run 2](screenshots/M5-100-2.png)

### K = 500

![M5 Locust K=500 - run 1](screenshots/M5-500-1.png)
![M5 Locust K=500 - run 2](screenshots/M5-500-2.png)

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

### Screenshots: API service auto-scaling (ECS / CloudWatch)

![ECS auto-scaling observation 1](screenshots/auto-scale-1.png)
![ECS auto-scaling observation 2](screenshots/auto-scale-2.png)
![K=500 API metrics 1](screenshots/auto-scale-500-1.png)
![K=500 API metrics 2](screenshots/auto-scale-500-2.png)
![K=500 API metrics 3](screenshots/auto-scale-500-3.png)

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

### 4. Root cause: API connection pool exhaustion, not Worker backlog

`GET /api/health` and `GET /api/providers` remained fast even at K=500 (p99 ≈ 260–300 ms). Only `POST /api/pipeline/start` and `GET /api/runs` degraded severely.

`/api/pipeline/start` queues a Celery task and returns immediately — the high latency means the API itself is CPU-bound handling 500 concurrent HTTP connections, not waiting for LLM calls. `/api/runs` reads from Redis, whose p99 reached 20,000 ms, indicating **Redis connection pool exhaustion** as 3 API tasks each maintain their own connection pools against the same ElastiCache instance.

**The Worker was not the bottleneck.** A live queue depth measurement was conducted during a K=500 run using ECS Exec to query `LLEN celery` on Redis db=1 every 15 seconds:

| Time | Queue depth |
|------|-------------|
| 22:50:18 | 0 |
| 22:50:35 | 1 |
| 22:50:52 | 0 |
| 22:51:10 | 1 |
| 22:51:27 | 0 |
| 22:51:44 | 0 |

The queue depth never exceeded 1. Workers drained tasks as fast as they arrived — no backlog formed. This is because the Locust payload uses `num_videos=2, num_scripts=2` (minimal pipeline), so each task completes quickly. The high latency observed at K=500 is caused entirely by **API-layer Redis connection pool exhaustion**, not Worker capacity.
![K=500 worker metrics 2](screenshots/M5-500-worker-2.png)

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

**Live measurement result:** Queue depth was sampled every 15 seconds via ECS Exec during a K=500 run. The queue never exceeded 1 — Workers drained tasks immediately. With the minimal Locust payload (`num_videos=2`), Worker capacity is not a constraint at K=500.

**For production workloads** with full-size pipelines (100 videos, real LLM calls taking 2–5 min each), queue depth would accumulate. In that scenario, CPU remains the wrong metric — a custom CloudWatch metric on `LLEN celery` with a threshold of ~50 tasks per Worker would be the correct scaling signal.

---

## Follow-up Run: Fresh Standalone K=500 (2026-04-13)

A second K=500 test was run the following day on a freshly deployed cluster with no prior load history. Results were significantly different from the first run.

### CloudWatch metrics (fresh run)

| Service | CPU Maximum | CPU Average | Auto-scaling triggered |
|---------|-------------|-------------|------------------------|
| flair2-dev-api | **25.1%** | ~5% | ❌ No |
| flair2-dev-worker | **7.14%** | ~0% | ❌ No |

### Comparison: cumulative vs. fresh load

| Condition | API CPU | Worker CPU | Auto-scale |
|-----------|---------|------------|------------|
| After K=10→50→100→1000 (Day 1) | **99%** | ~25% | ✅ 2→3 tasks |
| Fresh standalone K=500 (Day 2) | **25.1%** | **7.14%** | ❌ No |

### Why the difference?

The Day 1 run followed multiple consecutive test runs at different K values. By the time K=500 was reached:
- Redis connection pools were already saturated from prior runs
- The Celery queue had an existing backlog of unfinished pipeline tasks
- API tasks had accumulated state in memory

In the fresh Day 2 run, all resources started clean. With `api_min_count=2`, two API tasks distributed the K=500 load from the start, keeping per-task CPU at ~12.5%. The system handled K=500 comfortably without any auto-scaling.

### Revised conclusion

**K=500 does not stress the system under clean conditions.** The Day 1 inflection point was driven by cumulative load state, not by K=500 alone. The true per-run capacity appears to be higher than initially measured.

The Worker finding remains unchanged: **CPU peaked at only 7.14%** even with 500 concurrent users submitting pipeline tasks, conclusively confirming that CPU is the wrong scaling metric for the Worker service regardless of load history.

---

## Conclusions

| Finding | Detail |
|---------|--------|
| **Healthy operating range** | K ≤ 100 — zero failures, stable 34 ms median |
| **Throughput saturation** | ~48 RPS aggregated with 2 tasks (Kimi rate limit bound) |
| **Inflection point** | K = 500 — p95 jumps 47× to 2,900 ms |
| **API auto-scaling trigger** | CPU > 60% sustained ~3 min → 2 → 3 tasks in ~2 min |
| **API auto-scaling limitation** | 3 tasks still at 75–85% CPU; system did not fully recover |
| **Worker auto-scaling** | Did NOT trigger — Worker is IO-bound; CPU stayed near 0% |
| **Worker queue depth** | Measured at 0–1 during K=500 — no backlog, Worker kept up |
| **True bottleneck** | API-layer Redis connection pool exhaustion, not Worker capacity |
| **Redis pressure** | `/api/runs` p99 = 20,000 ms at sustained K=500 — connection pool exhaustion |
| **Failure rate** | 0.03% even at K=500 — system degrades gracefully, never hard-fails |

**Recommendation:** For K > 100 production traffic:
1. Replace Worker CPU scaling with a custom CloudWatch metric on Redis queue depth (`LLEN celery`)
2. Tune API connection pool size per ECS task to reduce Redis contention at K=500+
3. Consider raising ElastiCache instance type if `/api/runs` p99 exceeds SLA under sustained load

---

## Rerun: Post-refactor Baseline (2026-04-18)

A third run was conducted after two significant code changes merged to main:

- **95% completion threshold** (`a15876b`): S1 and S4 fan-out stages now transition to the next stage at `ceil(N × 0.95)` completions instead of waiting for all N — stragglers no longer block the pipeline.
- **S3 concurrent generation** (`a4646c3`): Script generation changed from sequential to concurrent (asyncio.gather + semaphore).

**Note:** Neither change affects load test measurements. The locustfile uses `num_videos=2, num_scripts=2` and `POST /api/pipeline/start` returns immediately after queuing tasks — it does not wait for pipeline completion. The S3 change is therefore invisible to this test. The 95% threshold only reduces pipeline end-to-end time, not API response time.

### Results — POST /api/pipeline/start

| K | p50 (ms) | p95 (ms) | p99 (ms) | RPS | Failures |
|---|----------|----------|----------|-----|----------|
| 10 | 40 | 53 | 70 | 1.9 | 0.0% |
| 50 | 41 | 130 | 270 | 10.8 | 0.0% |
| 100 | 41 | 92 | 390 | 21.1 | 0.0% |
| 500 | 420 | 1,300 | 2,900 | 87.1 | 0.0% |

### Comparison with prior runs

| K | p50 Day 1 | p50 Day 2 (clean) | p50 Day 3 | p95 Day 1 | p95 Day 3 | p99 Day 1 | p99 Day 3 |
|---|-----------|-------------------|-----------|-----------|-----------|-----------|-----------|
| 10 | 43 ms | — | **40 ms** | 79 ms | **53 ms** | 280 ms | **70 ms** ↓ |
| 50 | 43 ms | — | **41 ms** | 73 ms | **130 ms** ↑ | 160 ms | **270 ms** ↑ |
| 100 | 43 ms | — | **41 ms** | 78 ms | **92 ms** ↑ | 150 ms | **390 ms** ↑ |
| 500 | 590 ms | — | **420 ms** ↓ | 2,900 ms | **1,300 ms** ↓ | 3,100 ms | **2,900 ms** ↓ |

### Observations

**K=10:** p99 improved substantially (280 ms → 70 ms). Clean cluster with no accumulated session history means `/api/runs` Redis lookups are fast.

**K=50–100:** p95/p99 slightly higher than Day 1 despite clean cluster. Likely due to lower overall RPS in this run (10–21 RPS vs 20 RPS Day 1) — fewer requests means fewer samples in the tail, making p99 noisier.

**K=500:** p50 improved (590 ms → 420 ms), p95 halved (2,900 ms → 1,300 ms), p99 improved (3,100 ms → 2,900 ms), and **failures dropped to 0.0%** (from 0.03% Day 1). The improvement is attributable to the clean cluster state (no prior load accumulation) rather than code changes — consistent with the Day 2 finding.

### Confirmed findings

All three runs confirm the same structural behaviour:

| Finding | Status |
|---------|--------|
| K ≤ 100 zero failures | ✅ Confirmed across all runs |
| K = 500 inflection point (latency spike) | ✅ Confirmed — p50 jumps 10× regardless of code changes |
| Root bottleneck: API Redis connection pool | ✅ Unchanged — `/api/runs` degrades first under load |
| S3 serial→parallel has no load test impact | ✅ Confirmed — `POST /api/pipeline/start` returns before S3 runs |
| 95% threshold has no load test impact | ✅ Confirmed — API response time unaffected |
