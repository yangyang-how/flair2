# 16. Rate Limiting a Shared Upstream

> When multiple workers share one API key with a per-minute rate limit, you need centralized coordination. This article teaches the token bucket algorithm, its Redis implementation, and a documented race condition you should know about.

## The problem

Kimi (and most LLM providers) enforce a per-minute rate limit — say, 60 requests per minute per API key. Flair2 has multiple workers, all using the same API key. If each worker independently tracks "how many calls have I made this minute," the total would exceed the limit because they can't see each other's counts.

```
Worker A thinks: "I've made 20 calls this minute. 40 remaining."
Worker B thinks: "I've made 20 calls this minute. 40 remaining."
Worker C thinks: "I've made 20 calls this minute. 40 remaining."
Total: 60 calls this minute ← already at the limit
All three: "I still have room!" ← wrong, they've been counting independently
```

**The solution:** put the counter in a shared location that all workers access atomically. In Flair2, that's Redis.

## The token bucket algorithm

The rate limiter is a **token bucket**. The concept:

1. You have a bucket that holds `max_tokens` tokens (e.g., 60)
2. Tokens are added to the bucket at a fixed rate (e.g., 60 tokens per 60-second window)
3. Each API call consumes one token
4. If the bucket is empty, wait until tokens are replenished

Flair2 uses a simplified version: instead of continuous refilling, the bucket resets at the end of each window.

**File:** `backend/app/infra/rate_limiter.py`

```python
class TokenBucketRateLimiter:
    def __init__(self, redis, provider, max_tokens, window_seconds):
        self._redis = redis
        self._key = f"ratelimit:{provider}"
        self._max_tokens = max_tokens
        self._window_seconds = window_seconds

    async def acquire(self) -> bool:
        count = await self._redis.incr(self._key)
        if count == 1:
            await self._redis.expire(self._key, self._window_seconds)
        return count <= self._max_tokens

    async def wait_for_token(self, max_wait=30.0) -> None:
        elapsed = 0.0
        while elapsed < max_wait:
            if await self.acquire():
                return
            delay = 1.0 + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
            elapsed += delay
        raise RateLimitError(
            f"Rate limiter timed out after {max_wait}s waiting for {self._provider}",
            provider=self._provider,
        )
```

Let's break this down.

## `acquire()`: the core operation

```python
async def acquire(self) -> bool:
    count = await self._redis.incr(self._key)  # atomic increment
    if count == 1:
        await self._redis.expire(self._key, self._window_seconds)  # set TTL
    return count <= self._max_tokens
```

**`INCR` is atomic.** Redis guarantees that concurrent `INCR` operations on the same key are serialized. If 10 workers all call `INCR ratelimit:kimi` at the same instant, they get values 1 through 10, in some order, with no duplicates.

**`count == 1` means the key was just created.** The first `INCR` on a non-existent key creates it with value 1. When `count == 1`, we know this is the first request in a new window, so we set the TTL. After `window_seconds`, Redis automatically deletes the key, and the next `INCR` starts a new window.

**`count <= max_tokens` is the gate.** If the counter exceeds the limit, `acquire()` returns `False`. The caller should wait and retry.

## The documented race condition

The code comments call this out explicitly:

```
Note: INCR and EXPIRE are not atomic. If the process dies between them the
key has no TTL, so the next INCR will re-set it. This is an acceptable
edge-case for a prototype; fix with a Lua script if stricter guarantees are
needed.
```

**The race:** a worker calls `INCR` (count becomes 1), then crashes before calling `EXPIRE`. The key now has no TTL — it never expires. Every subsequent `INCR` increases the counter forever. Eventually `count > max_tokens`, and all workers are permanently locked out of the rate limiter.

**How likely is this?** Very unlikely. The crash window is the time between two Redis commands — microseconds. But "very unlikely" and "impossible" are different things in production at scale.

**The fix — Lua script:**

```lua
-- Atomic INCR + EXPIRE in one Redis call
local count = redis.call("INCR", KEYS[1])
if count == 1 then
    redis.call("EXPIRE", KEYS[1], ARGV[1])
end
return count
```

A Redis Lua script executes atomically — no crash window between INCR and EXPIRE. This is the production-grade solution. Flair2 documents the gap and accepts the risk for a prototype. This is good engineering: **know the weakness, document it, and make a conscious decision about when to fix it.**

## `wait_for_token()`: the blocking wrapper

```python
async def wait_for_token(self, max_wait=30.0):
    elapsed = 0.0
    while elapsed < max_wait:
        if await self.acquire():
            return
        delay = 1.0 + random.uniform(0, 0.5)
        await asyncio.sleep(delay)
        elapsed += delay
    raise RateLimitError(...)
```

If `acquire()` returns `False` (rate limit reached), wait 1-1.5 seconds and retry. The `random.uniform(0, 0.5)` adds jitter to prevent **thundering herd** — if 50 workers all hit the rate limit at the same time and all wait exactly 1 second, they'll all retry at the same time and hit the limit again. Jitter spreads the retries over a 0.5-second window.

**Timeout:** after 30 seconds of waiting, give up and raise `RateLimitError`. The task will fail, the orchestrator will mark the run as failed, the user sees an error. This prevents indefinite blocking — better to fail visibly than to hang silently.

## How tasks use the rate limiter

**File:** `backend/app/workers/tasks.py`

```python
async def _acquire_rate_limit_token(redis, provider_name):
    if not settings.enable_rate_limiter:
        return
    rpm = getattr(settings, f"{provider_name}_rpm", 60)
    limiter = TokenBucketRateLimiter(redis, provider_name, max_tokens=rpm, window_seconds=60)
    await limiter.wait_for_token()
```

Each task, before making an LLM call, waits for a rate limit token. The rate limit is per-provider (`ratelimit:kimi` is separate from `ratelimit:gemini`), and the max RPM comes from config (`kimi_rpm = 60` by default).

**`enable_rate_limiter` toggle:** the M5-1 backpressure experiment compared pipeline behavior with and without the rate limiter. The toggle lets you disable it for experimentation without changing code.

## Why centralized rate limiting

Let's look at the alternatives:

### Option 1: Per-worker rate limiting

Each worker tracks its own call count. If you have 4 workers with a 60 RPM limit, each worker allows 15 RPM.

**Problem:** worker count changes with auto-scaling. If ECS scales from 2 to 4 workers, each worker should drop from 30 to 15 RPM — but they don't know about each other. Over-provisioned workers waste budget; under-provisioned workers exceed the limit.

### Option 2: No rate limiting (let the provider reject)

Just call the API. If you get a 429, back off and retry.

**Problem:** the retry adds latency, the 429 wastes a round-trip, and if all workers get 429'd simultaneously, the retry storm can make things worse. Proactive rate limiting (check before calling) is almost always better than reactive rate limiting (call and handle rejection).

### Option 3: Centralized rate limiting (Flair2's approach)

One counter in Redis, shared by all workers. The counter accurately reflects total calls across all workers.

**Problem:** Redis is a dependency. If Redis is slow or down, the rate limiter blocks all LLM calls. But Flair2 already depends on Redis for everything else — the rate limiter doesn't add a new dependency, it reuses an existing one.

## What the M5-1 experiment proved

The backpressure experiment (in `tests/experiments/test_backpressure.py`) tested the rate limiter at different concurrency levels:

**Without rate limiter (K=10):** 90% of LLM calls were rejected with 429 errors. The pipeline crawled.

**With rate limiter (K=10):** 0% error rate. The rate limiter smoothed out the request pattern, keeping all workers within the budget.

**Fairness (measured by CV — coefficient of variation):** at K=1, CV was 1.36 (high variance in per-user completion time). At K=10, CV dropped to 0.40 (more uniform). **The rate limiter gets fairer as load increases** — counterintuitive but correct: with more contention, the random jitter in `wait_for_token` distributes work more evenly.

## Rate limiting patterns in the real world

| Pattern | Where you'll see it | How it works |
|---------|-------------------|-------------|
| **Token bucket** | API gateways, Stripe, AWS | Fixed refill rate, bursty-friendly |
| **Leaky bucket** | Traffic shaping, QoS | Constant output rate, no bursts |
| **Fixed window** | Flair2, simple APIs | Counter resets at window boundary |
| **Sliding window** | Sophisticated rate limiters | Rolling window, no boundary artifacts |

Flair2 uses **fixed window** (counter + TTL), which has a known edge case: at the boundary between two windows, you could make `max_tokens` calls in the last second of window 1 and `max_tokens` calls in the first second of window 2 — double the intended rate in a 2-second burst. **Sliding window** fixes this by counting calls in a rolling time period, but it's more complex to implement in Redis.

For Flair2's LLM calls (which take 2-5 seconds each), the boundary burst is impossible in practice — you can't make 60 calls in one second. The fixed window approximation is fine.

## What you should take from this

1. **Centralized rate limiting is required for shared upstreams.** Per-worker limits don't add up correctly when the worker count changes. Put the counter in a shared store.

2. **`INCR + EXPIRE` is the Redis idiom for fixed-window rate limiting.** Simple, fast, mostly atomic. For production, wrap it in a Lua script to eliminate the crash-window race.

3. **Jitter prevents thundering herd.** When many clients retry simultaneously, add random delay to spread them out. This applies to any retry logic, not just rate limiting.

4. **Document known weaknesses explicitly.** The non-atomic INCR/EXPIRE gap is called out in a code comment. This is better than silently shipping the bug — future developers know the risk and can decide when to fix it.

5. **The rate limiter is a shared resource too.** It uses a Redis key. If Redis itself is the bottleneck (as in the M5-4 experiment at K=500), the rate limiter becomes part of the problem — every task makes at least one Redis call just to check the rate limit before making any LLM call.

---

***Next: [Redis as the Nervous System](17-redis-nervous-system.md) — the five roles Redis plays, the data model, and why one server wearing five hats is both clever and dangerous.***
