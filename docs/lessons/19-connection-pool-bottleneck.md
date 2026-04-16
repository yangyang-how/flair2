# 19. The Connection Pool Bottleneck

> The most instructive failure in Flair2 isn't a bug — it's a resource that was invisible until it ran out. This article teaches you how to recognize resource exhaustion when no obvious metric is saturated.

## The symptom

M5-4 Locust load test, K=500 sustained:
- **API median latency:** 77ms (fine)
- **API p95 latency:** 12,000ms (catastrophic)
- **API p99 latency:** 18,000ms (18 seconds!)
- **Worker CPU:** 7.14% (idle)
- **Celery queue depth:** 0-1 tasks (no backlog)
- **Failures:** 18 requests failed

Everything looks fine individually. Worker CPU is near zero. The queue is empty. No single metric screams "overloaded." Yet 5% of requests take 12+ seconds. **What's dying?**

## The diagnosis

M6-2 ElastiCache SETNX atomicity experiment, K=5000:
- Tests pass at K=10, K=100, K=1000
- Tests fail at K=5000
- Failure mode: connections refused, not SETNX failures

Same root cause. Two experiments, two disguises:
- M5-4: API tasks couldn't get Redis connections → requests queued internally → tail latency exploded
- M6-2: Test processes couldn't get Redis connections → calls timed out → tests failed

**The bottleneck is the Redis connection pool.**

## What is a connection pool?

Every Redis call requires a TCP connection. Opening a TCP connection involves:
1. Three-way handshake (SYN, SYN-ACK, ACK)
2. TLS negotiation (if encrypted)
3. Redis AUTH command (if password-protected)
4. SELECT command (choose database)

This takes 1-5ms. For Redis operations that themselves take 0.5ms, the connection setup is 2-10x more expensive than the operation. Unacceptable for high-frequency calls.

**Solution: connection pooling.** Open N connections at startup, keep them alive, and reuse them across requests. Each Redis call borrows a connection from the pool, uses it, and returns it.

```
┌─────────────────────────────────┐
│        Connection Pool          │
│                                 │
│  ┌──────┐ ┌──────┐ ┌──────┐   │
│  │Conn 1│ │Conn 2│ │Conn 3│   │   (pool size = 10)
│  └──────┘ └──────┘ └──────┘   │
│  ┌──────┐ ┌──────┐ ┌──────┐   │
│  │Conn 4│ │Conn 5│ │Conn 6│   │
│  └──────┘ └──────┘ └──────┘   │
│  ┌──────┐ ┌──────┐ ┌──────┐   │
│  │Conn 7│ │Conn 8│ │Conn 9│   │
│  └──────┘ └──────┘ └──────┘   │
│  ┌───────┐                     │
│  │Conn 10│                     │
│  └───────┘                     │
└─────────────────────────────────┘
        ↑↑↑↑↑↑↑↑↑↑
    coroutines borrow and return
```

## How exhaustion happens

The `aioredis` library (used via `redis.asyncio`) creates a pool with a default `max_connections` (often 10-50, depending on version). Under async code, a single FastAPI process can have hundreds of coroutines in flight simultaneously — each `await redis.get(...)` borrows a connection, holds it for the round-trip (~0.5ms for local Redis, ~1-2ms for ElastiCache), and releases it.

When `coroutines_in_flight > max_connections`:

```
Coroutine 501: "I need a Redis connection"
Pool: "All 10 connections are in use. Wait."
Coroutine 501: (waits)
Coroutine 502: "I need a Redis connection"
Pool: "Still all 10 in use. Wait."
...
(queue grows, tail latency grows, eventually timeouts)
```

**The wait queue is invisible.** There's no dashboard metric for "coroutines waiting for a connection." CPU is low (coroutines are waiting, not computing). Memory is low (waiting coroutines are cheap). Network is low (no data is flowing while waiting). The only symptom is tail latency — which is what the M5-4 experiment measured.

## Why the API layer was hit hardest

Let's count Redis calls per API request:

**`POST /api/pipeline/start`:**
1. `SET run:{id}:config` (config)
2. `SET run:{id}:status` (status)
3. `SET run:{id}:stage` (stage)
4. `DELETE + SET` × 3 (counter initialization = 6 calls)
5. `XADD` × 2 (SSE events)
6. `RPUSH` (session tracking)
Total: ~12 Redis calls per start request

**`GET /api/pipeline/status/{run_id}`:**
1. `GET run:{id}:status` (existence check)
2. `XREAD` (blocking, 5 seconds, repeated) — holds a connection for 5 seconds!

**`GET /api/runs`:**
1. `LRANGE` (list run IDs)
2. `GET × N` (status of each run)

The SSE endpoint is the killer. `XREAD` blocks for up to 5 seconds per call, holding a connection the entire time. With 100 concurrent SSE connections and a pool of 10 connections — 90 SSE connections are queued, each waiting up to 5 seconds for a pool slot. That's where the 12-18 second p99 comes from.

## Why Workers weren't affected

Workers use a different `RedisClient` instance (created per-task in `tasks.py`), which creates its own connection pool. More importantly, each worker task makes 3-5 Redis calls that complete in milliseconds, then spends 2-5 seconds calling the LLM. The connection is returned to the pool before the LLM call. The duty cycle (time holding a connection / total task time) is very low.

The API's SSE connections are the opposite: they hold a connection for 5 seconds (blocking XREAD), return it briefly to check for disconnect, then immediately grab it again. The duty cycle is nearly 100%.

## The fix

### Fix 1: Size the pool properly

```python
# In deps.py:
_redis_pool = aioredis.from_url(
    settings.redis_url,
    decode_responses=True,
    max_connections=200,  # ← add this
)
```

**Rule of thumb:** `max_connections` should be at least the expected number of concurrent coroutines that hold a connection at any given time. For SSE, that's one per active viewer. For regular API calls, it's the concurrent request count × Redis calls per request.

### Fix 2: Separate pools for SSE and regular operations

```python
# SSE pool (long-held connections)
_sse_pool = aioredis.from_url(settings.redis_url, max_connections=100)

# API pool (short-lived connections)
_api_pool = aioredis.from_url(settings.redis_url, max_connections=50)
```

SSE connections and API request handling have fundamentally different connection profiles. Mixing them in one pool means SSE connections starve API requests (or vice versa). Separate pools provide isolation — a burst of SSE connections doesn't affect API response times.

### Fix 3: Connection timeout

```python
_redis_pool = aioredis.from_url(
    settings.redis_url,
    max_connections=200,
    socket_timeout=5.0,      # ← operation timeout
    socket_connect_timeout=2.0,  # ← connection establishment timeout
)
```

Without timeouts, a coroutine waiting for a pool slot waits forever (or until the client-side TCP timeout, which can be minutes). Explicit timeouts make failures visible and fast: "connection pool exhausted" in 2 seconds is better than "request hung for 60 seconds."

### Fix 4: Monitor the pool

Add metrics for:
- Pool size (total connections)
- In-use connections
- Waiting queue length
- Wait time (how long coroutines wait for a connection)

These are the metrics that would have identified the bottleneck immediately — instead of inferring it from tail latency patterns.

## The general lesson: invisible resources

The connection pool is an **invisible resource**. Unlike CPU (which has a utilization percentage), memory (which has a usage gauge), or network (which has bandwidth metrics), the connection pool's exhaustion doesn't appear on standard dashboards.

Other invisible resources you'll encounter:

| Resource | Where | Symptom of exhaustion |
|----------|-------|----------------------|
| **Connection pool** | Redis, Postgres, HTTP clients | Tail latency spikes, timeouts |
| **File descriptors** | Any process | "Too many open files" errors |
| **Thread pool** | Java web servers, Python `ThreadPoolExecutor` | Request queuing, increased latency |
| **Semaphores** | Rate limiters, concurrent access controls | Deadlocks, slow degradation |
| **DNS cache** | HTTP clients with many backends | Periodic latency spikes on cache miss |
| **TCP listen backlog** | Overloaded servers | Connection refused errors |

**The pattern is always the same:** a bounded pool of reusable resources, a usage rate that exceeds the pool size, and a queue that grows silently until it causes visible symptoms.

**How to find them:** when tail latency explodes but no obvious resource is saturated:
1. Ask: "what bounded resources exist between the client and the operation?"
2. Check if the bounded resource has a wait queue
3. Measure the queue length and wait time

In Flair2's case: the chain is `HTTP request → FastAPI coroutine → Redis pool → Redis connection → Redis server`. The server was fine. The connection was fine. The pool — the invisible middleman — was the bottleneck.

## What you should take from this

1. **Connection pools are invisible until they're exhausted.** No standard metric shows "pool utilization." You have to instrument it yourself.

2. **Tail latency is the canary.** Median latency can be fine while p99 is catastrophic. If p95/p99 diverge dramatically from the median, a bounded resource is probably saturated.

3. **Separate pools for separate workloads.** Long-held connections (SSE) and short-lived connections (API calls) should not share a pool. One workload will starve the other.

4. **Size pools to match concurrency, not throughput.** The pool size should match the number of concurrent connections needed, not the total requests per second. 1000 RPS with 1ms hold time needs 1 connection. 10 RPS with 5s hold time needs 50.

5. **"Add more instances" doesn't always help.** If every API instance has a 10-connection pool, adding a third instance gives you 30 total connections — but you might need 200. Scaling horizontally without fixing the pool size multiplies the problem by the number of instances.

---

***Next: [Terraform and the AWS Topology](20-terraform-aws-topology.md) — how infrastructure-as-code documents the architecture.***
