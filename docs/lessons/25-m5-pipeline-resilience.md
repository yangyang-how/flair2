# 25. M5: Pipeline Resilience

> Three experiments, three questions, seventeen tests. All run locally with fakeredis — no AWS required. This article walks through each experiment, what it tested, and what it proved.

## M5-1: Backpressure

**File:** `backend/tests/experiments/test_backpressure.py`

### The question

When K concurrent users share one LLM rate limit, does the rate limiter prevent API errors? How does it affect fairness between users?

### The design

**Independent variable:** K (concurrent pipeline runs): 1, 2, 5, 10
**Dependent variables:** LLM error rate, per-user completion time, coefficient of variation (CV) of completion times
**Control:** with vs without rate limiter (`settings.enable_rate_limiter = True/False`)

### What backpressure means

When demand exceeds capacity, the system has three choices:
1. **Drop requests** — fast, but users lose work
2. **Queue requests** — slower, but no data loss (until the queue fills)
3. **Apply backpressure** — slow down producers so they don't overwhelm consumers

The rate limiter implements backpressure: when too many LLM calls are in flight, `wait_for_token()` blocks the calling task until capacity is available. The task slows down rather than crashing. The pipeline runs slower, but it runs.

### Key results

**Without rate limiter, K=10:** 90% of LLM calls received 429 errors. The pipeline was essentially broken — most calls failed, most runs produced garbage.

**With rate limiter, K=10:** 0% error rate. The rate limiter throttled calls to stay within the budget. All runs completed successfully.

**Fairness (CV):** at K=1, CV was 1.36 (high variance — some runs much faster than others). At K=10, CV dropped to 0.40 (more uniform). This is counterintuitive: more contention → more fairness. The reason: the random jitter in `wait_for_token()` naturally distributes requests, and the rate limiter enforces equal access — no user can monopolize the budget.

### What this proves

1. **Centralized rate limiting is necessary, not optional.** Without it, concurrent users destroy each other's runs.
2. **Backpressure is preferable to failure.** A slower successful run beats a fast failed one.
3. **Rate limiting has a fairness side effect.** The token bucket naturally distributes capacity across users.

## M5-2: Failure Recovery

**File:** `backend/tests/experiments/test_failure_recovery.py`

### The question

When a worker crashes mid-S4, do sibling runs continue? How much work does checkpointing save?

### The design

**Test 1 — Sibling isolation:** start two pipeline runs concurrently. Kill the worker processing Run A mid-S4. Verify that Run B continues unaffected.

**Test 2 — Checkpoint savings:** start a run, kill the worker at various S4 completion percentages (30%, 50%, 73%). Call `recover()`. Count how many LLM calls were skipped.

### What "sibling isolation" means

In a shared-worker architecture, Run A and Run B's tasks are interleaved on the same workers. If Run A's tasks poison the worker (memory leak, crash), does Run B also fail?

In Flair2, the answer is no — because:
1. Each task is independent (no shared in-memory state between tasks)
2. `acks_late=True` means a crashed task is redelivered
3. The Celery broker tracks tasks per-run via the `run_id` parameter

Killing a worker kills the specific tasks it was executing, but other tasks for other runs (and even the same run) continue on other workers.

### Key results

**Sibling isolation:** Run B completed successfully every time, regardless of when Run A's worker was killed. The runs are truly independent.

**Checkpoint savings:**
- Crash at 30%: 30 LLM calls saved (out of 100)
- Crash at 50%: 50 calls saved
- Crash at 73%: 73 calls saved

**Range: 30-73% savings.** The later the crash, the more checkpointing saves. Average across random crash points: ~50%.

### What this proves

1. **Runs are isolated.** One run's failure doesn't cascade to others.
2. **Checkpointing provides proportional savings.** Savings scale linearly with progress at crash time.
3. **Recovery code works.** The `orchestrator.recover()` path was exercised and validated — it correctly reads the checkpoint and dispatches only remaining tasks.

## M5-3: Cache Concurrency

**File:** `backend/tests/experiments/test_cache_concurrency.py`

### The question

Does SETNX-based caching prevent redundant LLM calls under concurrent access? How do savings scale with K?

### The design

**Independent variable:** K (concurrent pipeline runs): 1, 10, 100, 1000, 100000
**Dependent variables:** SETNX call count (number of LLM calls actually made), total requests, savings percentage

**Setup:** all K runs analyze the same video dataset (100 videos). Without caching, each run makes 100 S1 calls. With caching, the first run computes; subsequent runs hit the cache.

### The theory

With SETNX caching:
- **First run:** all 100 calls are cache misses → 100 LLM calls
- **Subsequent runs:** all 100 calls are cache hits → 0 LLM calls
- **Total LLM calls:** 100, regardless of K

Without caching:
- **Each run:** 100 LLM calls
- **Total LLM calls:** K × 100

Savings: `1 - (100 / (K × 100))` = `1 - (1/K)`

### Key results

| K | Without cache | With cache | Savings |
|---|--------------|-----------|---------|
| 1 | 100 | 100 | 0% |
| 10 | 1,000 | 100 | 90% |
| 100 | 10,000 | 100 | 99% |
| 1,000 | 100,000 | 100 | 99.9% |
| 100,000 | 10,000,000 | 100 | 99.999% |

**SETNX call count is fixed at NUM_VIDEOS (100) regardless of K.** The cache serves all subsequent requests. The savings approach 100% as K grows.

### What this proves

1. **SETNX caching works as designed.** Only one worker computes per cache key, all others wait and receive the cached result.
2. **The savings are dramatic at scale.** At K=10, you save 90% of LLM costs. At K=100, 99%.
3. **The sentinel pattern prevents stampedes.** The winner/loser pattern with sentinel TTL, exception cleanup, and loser timeout handles all edge cases in testing.

### The caveat

This was tested with fakeredis — a single-process, single-threaded Redis simulator. Real concurrency (multiple processes, network latency, TCP connection management) introduces additional failure modes. M6-2 tested this on real ElastiCache and found that SETNX works at K=1000 but the connection pool fails at K=5000.

## How the tests are structured

All three experiments use pytest with parametrized test cases:

```python
@pytest.mark.parametrize("k", [1, 2, 5, 10])
async def test_backpressure_with_rate_limiter(k):
    ...
```

The tests use fakeredis for Redis operations, mock the LLM provider (return canned responses), and run async code with `asyncio`. No AWS resources needed.

**Test pyramid:** these are positioned between unit tests (testing individual functions) and production experiments (testing the deployed system). They test the interaction between multiple components (rate limiter + tasks + orchestrator) in a controlled environment.

## The value of local experiments

Running experiments locally with fakes has advantages:
- **Fast:** seconds, not minutes. You can iterate on the experiment design quickly.
- **Deterministic:** no network jitter, no provider rate limiting, no variable response times. Results are reproducible.
- **Free:** no cloud costs, no API costs.
- **Safe:** no risk of breaking production.

And disadvantages:
- **Missing real failure modes:** fakeredis doesn't have connection pools, network partitions, or memory limits. M6 exists specifically to test these.
- **Different timing:** fakeredis operations are microseconds, real Redis is milliseconds. Timing-sensitive behavior (race conditions, timeouts) may behave differently.
- **No scaling reality:** running K=100,000 in fakeredis is instant. Running it against ElastiCache would test real resource limits.

The right approach is both: local experiments for fast iteration, production experiments for validation. M5 proved the concepts; M6 validated them on real infrastructure.

## What you should take from this

1. **Three experiments, three different patterns.** A/B comparison (M5-1), failure injection (M5-2), and scaling test (M5-3). Each pattern answers a different type of question.

2. **Local fakes are great for concept validation.** fakeredis lets you test concurrent behavior without AWS. But acknowledge what fakes can't test.

3. **Quantify, don't guess.** "Checkpointing helps" is a guess. "Checkpointing saves 30-73% of LLM calls depending on crash timing" is evidence. The experiment transformed a design intuition into a measured fact.

4. **All 17 tests passed.** This validates the design decisions (rate limiting, checkpointing, SETNX caching) that the earlier articles explained. The experiments are the proof that the architecture works as intended.

5. **The experiments are the most educational part of the codebase.** Reading `test_backpressure.py` teaches you more about rate limiting than reading `rate_limiter.py`, because the test shows you the *behavior* — what happens with and without the mechanism under different conditions.

---

***Next: [M5-4: Load Testing with Locust](26-m5-4-locust.md) — the first experiment that broke the system.***
