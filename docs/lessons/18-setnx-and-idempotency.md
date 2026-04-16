# 18. SETNX and Idempotency

> When 10 concurrent pipeline runs all need to analyze the same video, you can call the LLM 10 times and get 10 identical results — or you can call it once, cache the result, and serve the other 9 from cache. SETNX is how you ensure only one caller does the work.

## The problem: cache stampede

Imagine 10 users start pipeline runs simultaneously. Each run's S1 stage needs to analyze video #42. Without caching, all 10 runs call the LLM with the same prompt for video #42. That's 10 identical API calls — 10x the time, 10x the cost, 10x the rate limit consumption.

The naive fix is: check the cache first, compute if missing, store the result.

```python
# Naive caching (race condition!)
result = await redis.get(cache_key)
if result is None:
    result = await compute()         # ← 10 workers all reach here simultaneously
    await redis.set(cache_key, result)
return result
```

**The race condition:** between checking the cache (`GET`) and setting it (`SET`), multiple workers all see "cache is empty" and all start computing. This is a **cache stampede** — the very problem caching was supposed to prevent.

## SETNX: Set if Not eXists

Redis `SETNX` (or `SET ... NX`) atomically sets a key only if it doesn't already exist. It returns `True` if the key was set (you're the first), `False` if it already existed (someone beat you).

```
Worker A: SETNX cache:video42 "computing"  → True  (winner)
Worker B: SETNX cache:video42 "computing"  → False (loser)
Worker C: SETNX cache:video42 "computing"  → False (loser)
```

Only Worker A proceeds to compute. Workers B and C know someone else is handling it.

## Flair2's implementation: the winner/loser pattern

**File:** `backend/app/infra/redis_client.py` — `cache_get_or_compute`

```python
CACHE_SENTINEL = "computing"
CACHE_SENTINEL_TTL = 60     # auto-expires if winner crashes
CACHE_POLL_INTERVAL = 0.5   # seconds between polls
CACHE_POLL_TIMEOUT = 30.0   # seconds before loser retries as winner

async def cache_get_or_compute(self, cache_key, compute_fn, ttl=3600):
    # Check cache
    cached = await self.get(cache_key)
    if cached is not None and cached != CACHE_SENTINEL:
        return cached  # Cache hit — return immediately

    # Try to become the winner
    if cached is None:
        won = await self.setnx(cache_key, CACHE_SENTINEL, ttl=CACHE_SENTINEL_TTL)
        if won:
            try:
                result = await compute_fn()
                await self.set(cache_key, result, ttl=ttl)
                return result
            except Exception:
                await self.delete(cache_key)  # Clean up sentinel on failure
                raise

    # Loser path: poll until value appears
    elapsed = 0.0
    while elapsed < CACHE_POLL_TIMEOUT:
        await asyncio.sleep(CACHE_POLL_INTERVAL)
        elapsed += CACHE_POLL_INTERVAL
        val = await self.get(cache_key)
        if val is not None and val != CACHE_SENTINEL:
            return val  # Winner finished — use their result

    # Timeout — retry as winner (sentinel TTL will eventually clear)
    return await self.cache_get_or_compute(cache_key, compute_fn, ttl)
```

This has three layers of defense against problems:

### Layer 1: Sentinel with TTL

The winner doesn't write the final result immediately — it writes a sentinel value (`"computing"`) with a 60-second TTL. This tells losers "someone is working on it." The TTL ensures that if the winner crashes, the sentinel expires automatically after 60 seconds, allowing a new winner.

### Layer 2: Winner cleans up on failure

```python
except Exception:
    await self.delete(cache_key)  # Remove sentinel so others can retry
    raise
```

If the computation fails (LLM error, timeout, etc.), the winner deletes the sentinel immediately. Losers who are polling will see `None` on their next check and can attempt to become the new winner.

### Layer 3: Loser timeout and retry

If a loser polls for 30 seconds and the sentinel is still there (winner is very slow or crashed and TTL hasn't fired yet), the loser recursively calls `cache_get_or_compute` to try becoming the winner. This prevents indefinite blocking.

The docstring in the code calls these out explicitly as a "three-layer defense against poison sentinels." This level of defensive design is what separates robust distributed code from code that "works in testing."

## The economics: M5-3 experiment

The cache concurrency experiment (`tests/experiments/test_cache_concurrency.py`) measured how many LLM calls SETNX caching actually saves:

| K (concurrent runs) | LLM calls without cache | LLM calls with cache | Savings |
|---------------------|------------------------|---------------------|---------|
| 1 | 100 (NUM_VIDEOS) | 100 | 0% (no sharing) |
| 10 | 1,000 | 100 | 90% |
| 100 | 10,000 | 100 | 99% |
| 1,000 | 100,000 | 100 | 99.9% |
| 100,000 | 10,000,000 | 100 | 99.999% |

**The SETNX call count is fixed at NUM_VIDEOS regardless of K.** Whether 10 users or 100,000 users analyze the same videos, the LLM is called exactly once per video. Every other request hits the cache.

**Why this works:** S1's cache key includes the video_id but NOT the run_id. All runs analyzing the same video share the same cache entry. This is correct because the S1 analysis of a given video doesn't depend on the run — it depends only on the video content.

## When caching IS appropriate

Not everything should be cached. The decision depends on two properties:

**1. Same input → same output?** S1 analysis of video #42 is the same regardless of which run requests it. Cache-friendly. But S4 voting depends on the persona_id AND the specific scripts generated in S3 — different runs may have different scripts, so the same persona_id in different runs should NOT share a cache.

**2. Stale data acceptable?** S1 results don't change — the video dataset is static. A cached result from 5 minutes ago is as good as a fresh one. But rate limiter state must be real-time — caching it would defeat the purpose.

| Stage | Cacheable? | Why |
|-------|-----------|-----|
| S1 | Yes | Same video → same patterns, regardless of run |
| S2 | Maybe | Depends on S1 results, which are cached. Same video set → same library |
| S3 | No | Depends on pattern library AND random generation — non-deterministic |
| S4 | No | Depends on specific scripts from S3, which vary per run |
| S5 | No | Depends on specific votes from S4, which vary per run |
| S6 | No | Depends on specific scripts and creator profile |

## SETNX vs other coordination primitives

### SETNX vs distributed locks (Redlock)

A distributed lock (like Redlock) provides mutual exclusion: only one process can hold the lock at a time. SETNX provides a similar "first one wins" guarantee, but simpler:

- **Lock:** acquire → do work → release. Must remember to release. Must handle lock expiry.
- **SETNX:** set if absent → do work → overwrite with result. No explicit release needed.

For caching, SETNX is simpler because the "lock" is the sentinel value, and the "release" is overwriting with the real value. There's no separate lock lifecycle to manage.

### SETNX vs atomic compare-and-swap (CAS)

CAS: "set the value to X only if the current value is Y." More general than SETNX (which is CAS where Y = "doesn't exist"). Flair2 doesn't need CAS because the only transition is "doesn't exist" → "computing" → "result."

## The sentinel pattern in the wild

| System | "Sentinel" equivalent | Winner/loser pattern |
|--------|--------------------|---------------------|
| **Flair2** | `"computing"` string with TTL | SETNX + poll |
| **Memcached** | Lock key + dog-piling prevention | Similar — "lease" mechanism |
| **CDN cache** | "Stale-while-revalidate" | Serve stale, one backend refreshes |
| **Database** | `SELECT ... FOR UPDATE` | Row lock, one writer |
| **Distributed systems** | Leader election | One leader, others follow |

The pattern is universal: **when N processes need the same result, elect one to compute it and have the others wait.**

## What you should take from this

1. **SETNX is the atomic "first one wins" primitive.** It eliminates cache stampedes by ensuring only one process computes a given result.

2. **Sentinels need TTLs.** Without a TTL, a crashed winner leaves a permanent sentinel that blocks all future attempts. The TTL is the safety net.

3. **Three-layer defense is the right depth.** Sentinel TTL (automatic cleanup) + exception cleanup (fast cleanup) + loser timeout (fallback). Each layer catches failures that the previous layer misses.

4. **Cache key design determines sharing.** Including `video_id` in the key allows cross-run sharing. Including `run_id` would prevent it. The key structure encodes your caching policy.

5. **The savings scale with concurrency.** At K=1, caching saves nothing. At K=10, it saves 90%. The return on investment grows with the number of concurrent users — which is exactly when you need it most.

---

***Next: [The Connection Pool Bottleneck](19-connection-pool-bottleneck.md) — the most interesting systems story in the whole project.***
