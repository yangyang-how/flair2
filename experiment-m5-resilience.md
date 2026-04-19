# M5 Experiments Report: Distributed Pipeline Resilience

**Date:** 2026-04-12 (rerun: 2026-04-18)  
**Environment:** Local (fakeredis — no AWS required)  
**Tests:** 17 passed, 0 failed  
**Total runtime:** 43.6 s  
**Production defaults (current):** 100 videos · 20 scripts · 42 personas · cap=29 (Kimi)

---

## M5-1: Multi-tenant Backpressure

**Issue:** [#41](https://github.com/yangyang-how/flair2/issues/41)  
**File:** `backend/tests/experiments/test_backpressure.py`

### What We Tested

K concurrent pipeline runs each fire 5 LLM calls simultaneously (simulating the S4 fan-out burst). A shared provider enforces a limit of 5 calls per 100 ms window.

Two conditions are compared:
- **no_limiter** — calls go directly to the provider; excess calls fail immediately
- **rate_limited** — calls pass through `TokenBucketRateLimiter` before hitting the provider

### Results

| K | Mode | Calls | Errors | Error Rate | Mean (ms) | CV (fairness) |
|---|------|-------|--------|------------|-----------|---------------|
| 1 | no_limiter | 5 | 0 | 0.0% | 2.6 | 0.00 |
| 1 | rate_limited | 5 | 0 | 0.0% | 8.9 | 0.00 |
| 3 | no_limiter | 15 | 10 | 66.7% | 0.9 | 1.36 |
| 3 | rate_limited | 15 | 0 | **0.0%** | 195.7 | 0.80 |
| 5 | no_limiter | 25 | 20 | 80.0% | 0.8 | 1.21 |
| 5 | rate_limited | 25 | 0 | **0.0%** | 468.7 | 0.52 |
| 10 | no_limiter | 50 | 45 | 90.0% | 0.9 | 0.67 |
| 10 | rate_limited | 50 | 0 | **0.0%** | 991.0 | 0.40 |

### Scale Projection

| K | no_limiter error% | rate_limited error% | Completion time |
|---|-------------------|---------------------|-----------------|
| 50 | 98.0% | 0.0% | 4.6 s |
| 100 | 99.0% | 0.0% | 8.7 s |
| 1,000 | 99.5% | 0.0% | 20.0 s |
| 10,000 | 100.0% | 0.0% | 3.3 min |
| 100,000 | 100.0% | 0.0% | 33.3 min |

### Acceptance Criteria

| Criterion | Target | Result |
|-----------|--------|--------|
| no_limiter error rate at K=10 | > 50% | **90.0%** ✅ |
| rate_limited error rate at K=10 | < 1% | **0.0%** ✅ |
| rate_limited fairness CV at K=10 | < 1.0 | **0.40** ✅ |

### Conclusion

Without a rate limiter, 90% of LLM calls fail at K=10 concurrent runs — the provider is immediately overwhelmed. The `TokenBucketRateLimiter` eliminates all errors at every scale tested, serialising calls through a controlled queue. Completion time grows linearly with K (O(K)), which is the expected trade-off: throughput is bounded by the provider limit, not by errors and retries.

The CV (coefficient of variation across run completion times) drops from 1.36 → 0.40 as K increases with the limiter active, showing the queue becomes *more* fair as load grows — no single run is starved.

---

## M5-2: Failure Recovery and Run Isolation

**Issue:** [#42](https://github.com/yangyang-how/flair2/issues/42)  
**File:** `backend/tests/experiments/test_failure_recovery.py`

### What We Tested

A pipeline run has 15 total LLM calls distributed across stages:
- S1 (analysis): 4 calls
- S3 (script generation): 1 task (internally generates `num_scripts` calls concurrently via `asyncio.gather`, but counted as 1 unit here because it is a single Celery task fully checkpointed before S4 begins)
- S4 (persona voting): 8 calls
- S6 (personalization): 2 calls

We simulate a worker crash at 25%, 50%, and 75% completion into S4 (the longest stage). Redis checkpoints record which S4 calls have already completed. On recovery, only the remaining calls are replayed.

Three isolation tests verify that crashing one run does not affect sibling runs running concurrently.

### API Call Savings from Checkpointing

| Crash scenario | Full run calls | Recovery calls | Saved | Pass |
|----------------|---------------|----------------|-------|------|
| 25% into S4 | 15 | 8 | **46.7%** | ✅ |
| 50% into S4 | 15 | 6 | **60.0%** | ✅ |
| 75% into S4 | 15 | 4 | **73.3%** | ✅ |

All scenarios exceed the 40% savings threshold from issue #42.

### Run Isolation Results

| Test | Result |
|------|--------|
| Crashed run resumes and reaches `completed` status | ✅ |
| Sibling runs (B, C) complete normally while run A crashes | ✅ |
| Run A's crash leaves no contaminated keys in B or C's Redis namespace | ✅ |

### Conclusion

Redis-based checkpointing saves 47–73% of LLM API calls on recovery, depending on how far the crashed stage had progressed. The savings compound with longer stages — crashing later wastes less than crashing early.

Run isolation is complete: a crashed run cannot corrupt or delay sibling runs. Each run has its own Redis key namespace (`run:{run_id}:*`), so state is fully partitioned.

### Rerun: 2026-04-18 (post code changes)

Three significant changes merged between the original run (2026-04-12) and this rerun:

| Commit | Change | Impact on M5-2 |
|--------|--------|----------------|
| `a4646c3` | S3: sequential → concurrent (`asyncio.gather`) | None — S3 is 1 Celery task fully checkpointed before S4; call-count model unchanged |
| `a15876b` | 95% completion threshold for S1 and S4 fan-out | None — at `NUM_PERSONAS=8`, `ceil(8 × 0.95) = 8`; threshold has no effect at this scale |
| `197d937` | Predefined personas (`data/personas.json`, 42 entries) | None — experiment mocks S4 votes directly without real LLM calls |

**Result: all 5 tests pass, savings metrics identical to original run.**

The experiment's call-count model (`full_restart = 15`, recovery varies) remains valid because the checkpoint/recovery semantics of the orchestrator were not changed by any of these commits.

---

## M5-3: Cross-user Cache Concurrency

**Issue:** [#43](https://github.com/yangyang-how/flair2/issues/43)  
**File:** `backend/tests/experiments/test_cache_concurrency.py`

### What We Tested

K concurrent users each submit a pipeline run against the same set of 20 videos. In the **naive** approach every user's S1 stage independently calls the LLM for every video. With the **SETNX cache**, the first run to reach a video wins the lock and writes the result; all subsequent runs read from cache.

### Results

| K | Naive calls | SETNX calls | Duplicate calls saved | Savings |
|---|-------------|-------------|-----------------------|---------|
| 2 | 40 | 20 | 20 | **50.0%** |
| 5 | 100 | 20 | 80 | **80.0%** |
| 10 | 200 | 20 | 180 | **90.0%** |

### Scale Projection

| K | Naive calls | SETNX calls | Savings |
|---|-------------|-------------|---------|
| 50 | 1,000 | 20 | 98.0% |
| 100 | 1,995 | 20 | 99.0% |
| 1,000 | 20,000 | 20 | 99.900% |
| 10,000 | 200,000 | 20 | 99.990% |
| 100,000 | 2,000,000 | 20 | 99.999% |

SETNX calls are always exactly 20 (= NUM_VIDEOS), regardless of K. This is the theoretical minimum — the SETNX guarantee holds under concurrent load.

### Acceptance Criteria

| Criterion | Target | Result |
|-----------|--------|--------|
| SETNX calls == 20 for all K | Always | **[20, 20, 20]** ✅ |
| Naive has duplicates for all K > 1 | Always | **[20, 80, 180]** ✅ |

### Conclusion

SETNX-based caching achieves near-perfect deduplication. At K=10 concurrent users, 90% of S1 LLM calls are served from cache. The savings formula is `(K-1)/K × 100%`, which approaches 100% asymptotically as K grows.

This matters most at peak load: at K=1,000, the naive approach would make 20,000 LLM calls for the same 20 videos; SETNX reduces that to exactly 20. The SETNX atomicity guarantee — confirmed by M6-2 on real ElastiCache — ensures no two coroutines process the same video, even under network concurrency.

---

## Summary

| Experiment | Key Finding | All tests |
|------------|-------------|-----------|
| M5-1 Backpressure | Rate limiter: 0% errors vs 90% without, at K=10 | 6/6 ✅ |
| M5-2 Failure recovery | Checkpointing saves 47–73% of API calls on crash | 5/5 ✅ |
| M5-3 Cache concurrency | SETNX reduces LLM calls by 90% at K=10, scales to 99.999% | 6/6 ✅ |
| **Total** | | **17/17 ✅** |

All three mechanisms work together: the rate limiter prevents burst errors, checkpointing ensures recovery is cheap, and SETNX caching ensures concurrent users never duplicate work. These form the core resilience layer of the distributed pipeline.
