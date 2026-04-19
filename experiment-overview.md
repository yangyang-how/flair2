# CS6650 Distributed Systems — Experiment Overview

**Project:** Flair2 — AI Campaign Studio  
**Team:** Sam Wu, Jess Zhang  
**Repository:** [github.com/yangyang-how/flair2](https://github.com/yangyang-how/flair2)  
**Date:** April 2026

---

## System Summary

Flair2 is a six-stage distributed AI pipeline that extracts structural patterns from viral videos, generates candidate scripts, evaluates them through simulated crowd voting, and personalizes top performers to a creator's voice. The system runs on AWS ECS Fargate with ElastiCache Redis as the shared state layer and Celery as the task queue.

```
S1 (Map)    → Analyze videos          → extract patterns per video      [fan-out, N=100]
S2 (Reduce) → Aggregate patterns      → unified pattern library         [single task]
S3          → Generate scripts        → candidate scripts (concurrent)  [N=20, asyncio.gather]
S4 (Map)    → Persona voting          → each persona votes on scripts   [fan-out, N=42, cap=29]
S5 (Reduce) → Rank by Borda score     → top-N candidates selected       [single task]
S6          → Personalize             → adapt to creator voice           [fan-out, N=top_n]
```

A full production run (100 videos, 20 scripts, 42 personas) makes ~162 LLM API calls. The LLM API rate limit — not compute or network — is the dominant performance constraint.

---

## Experiments

Seven experiments across four groups, targeting distributed systems challenges that emerge from running AI workloads with shared resources at scale.

---

### Distributed Systems Core Patterns (Local, fakeredis + asyncio simulation)

**File:** [`experiment-distributed-patterns.md`](experiment-distributed-patterns.md)

These three experiments validate the core architectural decisions of the pipeline — the patterns that motivate the fan-out design, the idempotency mechanism, and the straggler threshold.

| Experiment | Question | Result |
|------------|----------|--------|
| **Fan-out Parallelism** | Does the S1/S4 fan-out achieve near-linear speedup? What is the Amdahl ceiling? | N=42, cap=29 (Kimi limit): **26× speedup, 90.7% efficiency**. Speedup plateaus at cap=N (Amdahl ceiling confirmed) |
| **Exactly-once Delivery** | Does the S4 idempotency check prevent duplicate LLM calls under Celery at-least-once delivery? | Sequential retries: always **1 LLM call**. 42 personas × 5 retries = 42 calls (not 210). Concurrent race is a known limitation of check-then-act — not a production scenario |
| **Straggler Mitigation** | Does the 95% completion threshold reduce pipeline latency when a few tasks take much longer? | Severe stragglers (10× median): **89.6% time saved**. S4 production config (N=42, 2 stragglers at 10×): **89.7% saved**. Zero overhead without stragglers |

15/15 tests passed. No AWS required.

---

### M5: Pipeline Resilience (Local, fakeredis)

**File:** [`experiment-m5-resilience.md`](experiment-m5-resilience.md)

| Experiment | Question | Result |
|------------|----------|--------|
| **M5-1 Backpressure** | How does the system behave when K concurrent users share one LLM rate limit? | Rate limiter holds error rate at 0% vs 90% without it at K=10. CV drops from 1.36→0.40 (fairer as load grows) |
| **M5-2 Failure Recovery** | When a worker crashes mid-S4, do sibling runs continue? How much does checkpointing save? | Sibling runs unaffected. Checkpointing saves 47–73% of API calls depending on crash timing |
| **M5-3 Cache Concurrency** | Does SETNX-based caching prevent redundant LLM calls under concurrent access? | SETNX calls fixed at NUM_VIDEOS regardless of K. 90% savings at K=10, approaching 99.999% at K=100,000 |

17/17 tests passed. No AWS required — uses fakeredis.

---

### M5-4: API Concurrent Load Test (AWS, Locust)

**File:** [`experiment-m5-load-test.md`](experiment-m5-load-test.md)

Locust simulated K=10–500 concurrent users against the deployed ALB on AWS ECS Fargate. Run three times: Day 1 (cumulative load), Day 2 (clean cluster), Day 3 (post S3-parallel + 95% threshold).

| K | p50 | p95 | p99 | RPS | Failures |
|---|-----|-----|-----|-----|----------|
| 10 | 35 ms | 51 ms | 190 ms | 4.81 | 0% |
| 50 | 35 ms | 59 ms | 100 ms | 48.24 | 0% |
| 100 | 34 ms | 61 ms | 140 ms | 47.96 | 0% |
| 500 (Day 1) | 69 ms | 2,900 ms | 4,200 ms | 175.89 | 0.03% |
| 500 (Day 3, clean) | 420 ms | 1,300 ms | 2,900 ms | 87.1 | 0% |

**Key findings:**
- System stable at K ≤ 100 with zero failures and 34 ms median
- K = 500 is the inflection point — p95 jumps sharply regardless of code changes
- True bottleneck: Redis connection pool exhaustion in the API layer, not Worker capacity
- Worker CPU peaked at 7.14% — IO-bound waiting on LLM, not CPU-bound
- S3 parallel + 95% threshold have **no effect** on load test results: `POST /api/pipeline/start` returns immediately before S3 runs

---

### M6: ElastiCache Integration (AWS, real Redis)

**File:** [`experiment-m6-elasticache.md`](experiment-m6-elasticache.md)

| Experiment | Question | Result |
|------------|----------|--------|
| **M6-1 Network Latency** | What is p50/p95/p99 latency for core Redis ops on ElastiCache vs fakeredis? | SETNX p50 ≈ 0.8 ms, p99 < 2 ms. ~10× slower than fakeredis but within SLA |
| **M6-2 SETNX Atomicity** | Does SETNX guarantee exactly one winner under real concurrent load? | Exactly 1 winner at K=10–1,000. Fails at K=5,000 due to aioredis connection pool exhaustion — not a Redis server fault |
| **M6-3 Memory Pressure** | Does memory scale linearly and stay within instance limits? | ~1 KB/key, linear scaling. cache.t3.micro safe to ~300 concurrent runs |

27/29 tests passed. 2 expected failures at K=5,000 (connection pool boundary — documented).

---

## Cross-Experiment Findings

**1. Fan-out parallelism is the system's primary throughput mechanism**
The distributed-patterns Fan-out experiment quantifies why S1 and S4 are designed as fan-out stages: N=42 personas complete in 1 latency unit instead of 42. Cap=29 (Kimi limit) gives 26× speedup. Without fan-out, a full pipeline run would take 42× longer at S4 alone.

**2. 95% threshold eliminates tail latency at no cost**
The Straggler Mitigation experiment shows that under severe stragglers (10× median — realistic for LLM rate-limit backoff), the 95% threshold saves 89.6% of pipeline waiting time. Without stragglers, overhead is <2%. This is the distributed systems equivalent of speculative execution.

**3. Redis connection pool is the system-wide bottleneck at scale**
Both M5-4 (API `/api/runs` p99 = 20,000 ms at K=500) and M6-2 (SETNX failures at K=5,000) point to the same root cause: too many concurrent coroutines competing for a limited pool of Redis connections.

**4. CPU is the wrong auto-scaling metric for Workers**
Worker CPU stayed near 0% even under K=500 load (7.14% peak). Workers spend most of their time waiting for LLM API responses (IO-bound). The correct scaling signal is Redis Celery queue depth (`LLEN celery`), not CPU.

**5. fakeredis hides real distributed failure modes**
M6-2 confirmed that SETNX atomicity trivially holds in fakeredis (single-threaded, no real concurrency) but fails at K=5,000 on real ElastiCache due to client-side connection pool issues — invisible in unit tests.

**6. Idempotency scope is limited to sequential retries**
The exactly-once experiment confirms the S4 check-then-act guard works for Celery's sequential at-least-once redelivery (the intended use case). Concurrent identical dispatches expose a race condition — but this scenario cannot occur in production because the orchestrator dispatches each (run_id, persona_id) pair exactly once.

---

## Infrastructure

| Component | Service | Config |
|-----------|---------|--------|
| Compute | AWS ECS Fargate | API: min=2/max=6, CPU target=60%; Worker: min=2/max=10, CPU target=70% |
| Cache / Queue | AWS ElastiCache Redis | cache.t3.micro, db=0 (state), db=1 (Celery broker) |
| Load Balancer | AWS ALB | flair2-dev-alb, us-west-2 |
| Storage | AWS S3 + DynamoDB | Pipeline outputs + run metadata |
| CI/CD | GitHub Actions | CI → Deploy → Integration Tests on every merge to main |

## Test Summary

| Group | File | Tests | Status |
|-------|------|-------|--------|
| Distributed Patterns | experiment-distributed-patterns.md | 15 | ✅ 15/15 |
| M5 Resilience | experiment-m5-resilience.md | 17 | ✅ 17/17 |
| M5-4 Load Test | experiment-m5-load-test.md | Live (Locust) | ✅ 3 runs |
| M6 ElastiCache | experiment-m6-elasticache.md | 29 | ✅ 27/29 (2 boundary) |
| **Total** | | **61 + 3 live runs** | **✅** |
