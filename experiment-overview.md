# CS6650 Distributed Systems — Experiment Overview

**Project:** Flair2 — AI Campaign Studio  
**Team:** Sam Wu, Jess Zhang  
**Repository:** [github.com/yangyang-how/flair2](https://github.com/yangyang-how/flair2)  
**Date:** April 2026

---

## System Summary

Flair2 is a six-stage distributed AI pipeline that extracts structural patterns from viral videos, generates candidate scripts, evaluates them through simulated crowd voting, and personalizes top performers to a creator's voice. The system runs on AWS ECS Fargate with ElastiCache Redis as the shared state layer and Celery as the task queue.

```
S1 (Map)    → Analyze videos          → extract patterns per video
S2 (Reduce) → Aggregate patterns      → unified pattern library
S3          → Generate scripts        → candidate scripts from patterns
S4 (Map)    → Persona voting          → each persona votes on each script
S5 (Reduce) → Rank by score           → top N candidates selected
S6          → Personalize             → adapt to creator voice + video prompt
```

A full production run (100 videos, 50 scripts, 100 personas) makes ~261 LLM API calls and ~500K tokens. The LLM API rate limit — not compute or network — is the dominant performance constraint.

---

## Experiments

We designed four experiments targeting genuine distributed systems challenges that emerge from running AI workloads with shared resources at scale.

### M5: Pipeline Resilience (Local, fakeredis)

**File:** [`experiment-m5-resilience.md`](experiment-m5-resilience.md)

| Experiment | Question | Result |
|------------|----------|--------|
| **M5-1 Backpressure** | How does the system behave when K concurrent users share one LLM rate limit? | Rate limiter holds error rate at 0% vs 90% without it at K=10. CV drops from 1.36→0.40 (fairer as load grows) |
| **M5-2 Failure Recovery** | When a worker crashes mid-S4, do sibling runs continue? How much does checkpointing save? | Sibling runs unaffected. Checkpointing saves 47–73% of API calls depending on crash timing |
| **M5-3 Cache Concurrency** | Does SETNX-based caching prevent redundant LLM calls under concurrent access? | SETNX calls fixed at NUM_VIDEOS regardless of K. 90% savings at K=10, approaching 99.999% at K=100,000 |

All 17 tests passed. No AWS required — uses fakeredis.

---

### M5-4: API Concurrent Load Test (AWS, Locust)

**File:** [`experiment-m5-load-test.md`](experiment-m5-load-test.md)

Locust simulated K=10–500 concurrent users against the deployed ALB on AWS ECS Fargate.

| K | Median | p95 | p99 | RPS | Failures |
|---|--------|-----|-----|-----|----------|
| 10 | 35 ms | 51 ms | 190 ms | 4.81 | 0 |
| 50 | 35 ms | 59 ms | 100 ms | 48.24 | 0 |
| 100 | 34 ms | 61 ms | 140 ms | 47.96 | 0 |
| 500 (60s) | 69 ms | 2,900 ms | 4,200 ms | 175.89 | 4 |
| 500 (sustained) | 77 ms | 12,000 ms | 18,000 ms | 130.18 | 18 |

**Key findings:**
- System stable at K ≤ 100 with zero failures and 34 ms median
- K = 500 is the inflection point — p95 jumps 47×
- API auto-scaling triggered at CPU > 60%, adding a 3rd ECS task in ~2 min
- Worker CPU peaked at 7.14% — Worker is IO-bound (waiting on LLM API), not CPU-bound
- Live queue depth measurement (ECS Exec → `LLEN celery`) confirmed 0–1 tasks in queue — no Worker backlog
- True bottleneck: Redis connection pool exhaustion in the API layer, not Worker capacity

---

### M6: ElastiCache Integration (AWS, real Redis)

**File:** [`experiment-m6-elasticache.md`](experiment-m6-elasticache.md)

Three experiments validating ElastiCache Redis as the shared state layer, replacing the fakeredis used in unit tests.

| Experiment | Question | Result |
|------------|----------|--------|
| **M6-1 Network Latency** | What is p50/p95/p99 latency for core Redis ops on ElastiCache vs fakeredis? | SETNX p50 = 0.4–0.5 ms, p99 < 2 ms. ~10× slower than fakeredis (0.05 ms) but well within SLA |
| **M6-2 SETNX Atomicity** | Does SETNX guarantee exactly one winner under real concurrent load? | Exactly 1 winner at K=10–1000. Fails at K=5000 due to connection pool exhaustion — not a Redis server fault |
| **M6-3 Memory Pressure** | Does memory stay within instance limits under 100 concurrent pipeline runs writing 100 keys each? | Peak usage stays well below cache.t3.micro limit across all tested scales |

27/29 tests passed. 2 failures at K=5000 (connection pool exhaustion — documented as expected boundary).

---

## Cross-Experiment Findings

**1. Redis connection pool is the system-wide bottleneck at scale**  
Both M5-4 (API `/api/runs` p99 = 20,000 ms) and M6-2 (SETNX failures at K=5000) point to the same root cause: too many concurrent coroutines competing for a limited pool of Redis connections. The fix is connection pool sizing, not instance scaling.

**2. CPU is the wrong auto-scaling metric for Workers**  
Worker CPU stayed near 0% even under K=500 load (7.14% peak). Workers spend most of their time waiting for LLM API responses (IO-bound). The correct scaling signal is Redis Celery queue depth (`LLEN celery`), not CPU.

**3. fakeredis hides real distributed failure modes**  
M6-2 confirmed that SETNX atomicity trivially holds in fakeredis (single-threaded event loop, no real concurrency) but requires real network validation. The K=5000 failure mode is invisible in unit tests.

**4. Auto-scaling works but needs tuning**  
ECS auto-scaling correctly detected CPU overload and added a 3rd API task within ~2 minutes. However, the 60% CPU target was still exceeded with 3 tasks at K=500 — the target or cooldown period needs adjustment for sustained high-concurrency workloads.

---

## Infrastructure

| Component | Service | Config |
|-----------|---------|--------|
| Compute | AWS ECS Fargate | API: min=2/max=6 tasks, CPU target=60%; Worker: min=2/max=4, CPU target=70% |
| Cache / Queue | AWS ElastiCache Redis | cache.t3.micro, Redis db=0 (state), db=1 (Celery broker) |
| Load Balancer | AWS ALB | flair2-dev-alb, us-west-2 |
| Storage | AWS S3 + DynamoDB | Pipeline outputs + run metadata |
| CI/CD | GitHub Actions | Deploy → Integration Tests on every merge to main |
