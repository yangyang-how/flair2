# 27. M6: ElastiCache Under Real Concurrency

> The M5 experiments proved the system works in theory (fakeredis). The M6 experiments tested whether it works in practice (ElastiCache). The answer: mostly yes, with one important caveat.

## Why real Redis matters

fakeredis is a Python implementation of Redis that runs in the same process as your tests. It's useful for unit testing because it's fast, requires no external dependencies, and provides the same API surface.

But fakeredis has blind spots:

| Property | fakeredis | Real Redis (ElastiCache) |
|----------|-----------|-------------------------|
| Network latency | 0 (in-process) | 0.4-2ms (VPC network) |
| Concurrency model | Single-threaded Python | Single-threaded C, but real TCP connections |
| Connection pool | Not applicable | Real pool with limits |
| Memory limits | Python process memory | Instance memory (t3.micro ≈ 500MB) |
| SETNX atomicity | Trivially guaranteed (no real concurrency) | Guaranteed at server, but connection pool can interfere |

**The fundamental issue:** fakeredis can't simulate the failure modes that arise from network boundaries — connection exhaustion, TCP timeouts, packet reordering, real memory pressure. M6 exists to test these.

## M6-1: Network Latency

**File:** `backend/tests/experiments/test_elasticache_integration.py`

### The question

What is the real-world latency for core Redis operations (SET, GET, SETNX, INCR, XADD) on ElastiCache, and how does it compare to fakeredis?

### The design

Run each operation 100 times against ElastiCache, measure p50, p95, and p99 latency.

### Key results

| Operation | ElastiCache p50 | ElastiCache p99 | fakeredis p50 |
|-----------|----------------|----------------|---------------|
| SET | 0.4 ms | 1.5 ms | 0.05 ms |
| GET | 0.3 ms | 1.2 ms | 0.04 ms |
| SETNX | 0.4-0.5 ms | < 2 ms | 0.05 ms |
| INCR | 0.3 ms | 1.0 ms | 0.04 ms |
| XADD | 0.5 ms | 2.0 ms | 0.06 ms |

**ElastiCache is ~10x slower than fakeredis.** This is expected — every operation involves a TCP round-trip across the VPC network. The absolute values are fast (sub-millisecond median), but the relative difference matters: any code path that makes many sequential Redis calls will be 10x slower on real Redis.

### What this means for the pipeline

A task that makes 5 sequential Redis calls (load config → rate limit check → LLM call → store result → notify orchestrator) adds ~2ms of Redis overhead with ElastiCache vs ~0.25ms with fakeredis. For tasks that take 2-5 seconds (dominated by LLM latency), the Redis overhead is negligible — less than 0.1% of total task time.

But for operations that make many rapid Redis calls (like dispatching 100 tasks, each requiring a Redis write), the overhead compounds: 100 × 0.5ms = 50ms total. Still fast, but a 10x increase from the 5ms you'd see with fakeredis.

**Lesson:** benchmark real infrastructure early. If your architecture assumes "Redis calls are free," ElastiCache will surprise you.

## M6-2: SETNX Atomicity

### The question

Does SETNX guarantee exactly one winner under real concurrent load on ElastiCache?

### The design

Run K concurrent coroutines, each calling `SETNX` on the same key. Count how many winners (SETNX returns True). The correct answer is exactly 1, regardless of K.

**Test points:** K = 10, 50, 100, 500, 1000, 5000

### Key results

| K | Winners | Correct? |
|---|---------|----------|
| 10 | 1 | Yes |
| 50 | 1 | Yes |
| 100 | 1 | Yes |
| 500 | 1 | Yes |
| 1,000 | 1 | Yes |
| 5,000 | **Failure** | Connection pool exhausted |

**K=10 through K=1,000: exactly 1 winner every time.** SETNX atomicity is rock-solid on real Redis. The Redis server serializes all SETNX calls and guarantees at most one succeeds per key.

**K=5,000: test failure.** Not because SETNX stopped being atomic — Redis SETNX is always atomic. The failure was in the client: 5,000 concurrent coroutines couldn't all get TCP connections to Redis. Connections timed out before the SETNX call was even sent.

### Why K=5,000 failed

The default `aioredis` connection pool has `max_connections` of ~50-100 (version-dependent). With 5,000 coroutines each needing a connection:

```
Coroutines 1-50:     Get connections, execute SETNX
Coroutines 51-5000:  Wait for connections...
                     Wait...
                     Some timeout → ConnectionError
```

The Redis server was fine. The TCP connections were fine. The pool was too small. This is the same bottleneck that M5-4 found at K=500 in the API layer — just manifested differently.

### The connection between M5-4 and M6-2

| Experiment | K at failure | Failure symptom | Root cause |
|------------|-------------|-----------------|-----------|
| M5-4 | 500 | API p99 = 18s | API Redis pool too small for SSE connections |
| M6-2 | 5,000 | SETNX test failure | Test Redis pool too small for concurrent calls |

**Same bug. Two experiments. Two disguises.** Both point to: `max_connections` in the Redis client pool is too small for the concurrency level.

The M6-2 documentation marks the K=5,000 failure as "expected boundary" — a known limitation of the client configuration, not a Redis server issue.

## M6-3: Memory Pressure

### The question

Does memory stay within instance limits under concurrent pipeline runs writing many keys?

### The design

Simulate 100 concurrent pipeline runs, each writing 100 keys to ElastiCache. Monitor Redis memory usage. Verify it stays within `cache.t3.micro` limits.

### Key results

Peak memory usage stayed well within the `cache.t3.micro` limit across all tested scales. Each pipeline run's data (config, stage results, SSE stream entries) is small — a few hundred KB total. 100 concurrent runs produce ~10MB of data. The `cache.t3.micro` instance has ~500MB available. No risk of memory exhaustion at the current scale.

### What would change at scale

At K=10,000 concurrent runs:
- Data: ~1GB (could approach instance limits)
- SSE Streams: each stream grows linearly with pipeline duration. 10,000 streams retained for 24 hours would consume significant memory.
- Mitigation: trim streams after terminal events (`XTRIM`), reduce TTL, or upgrade instance size.

**Lesson:** memory pressure is a function of concurrent data volume × retention time. Short TTLs and stream trimming are the first line of defense.

## What fakeredis hides

The M6 experiments revealed three things that fakeredis cannot show:

**1. Connection limits are real.** fakeredis has no TCP connections, no pool, no limits. Real Redis has all three. Any test of concurrent behavior on fakeredis gives false confidence about scalability.

**2. Network latency is non-zero.** Operations that are "instant" on fakeredis take 0.3-2ms on ElastiCache. Multiply by hundreds of operations per pipeline run and you get measurable overhead.

**3. Memory is finite.** fakeredis uses Python heap memory, which grows as needed. ElastiCache has a fixed memory limit that, once exceeded, triggers eviction or rejection.

**The general principle:** test doubles (fakes, mocks, stubs) verify logic. Only real infrastructure verifies behavior. You need both, and you need to know which failure modes each one can and cannot reveal.

## How the tests run on real infrastructure

The M6 tests are in `backend/tests/experiments/test_elasticache_integration.py`. They run against the deployed ElastiCache instance in the CI/CD pipeline (post-deployment), using the real Redis endpoint from the ECS environment.

```python
@pytest.fixture
async def redis():
    """Connect to ElastiCache (real Redis, not fakeredis)."""
    url = os.environ.get("ELASTICACHE_URL", "redis://localhost:6379/0")
    r = await aioredis.from_url(url, decode_responses=True)
    yield r
    await r.aclose()
```

The parametrized test approach (testing across K=10, 50, 100, ..., 5000) makes it easy to identify the exact boundary where behavior changes. This is the scaling test pattern from [Article 24](24-designing-experiments.md).

## What you should take from this

1. **Unit tests with fakes verify logic, not system behavior.** Always validate on real infrastructure before claiming the system works.

2. **SETNX atomicity is guaranteed by Redis, not by your client.** The server never fails to serialize SETNX. But your client might not be able to reach the server, which looks the same to your code.

3. **Connection pool exhaustion is the #1 hidden failure mode.** M5-4 and M6-2 both found it. If you take one thing from these experiments: instrument and size your connection pools.

4. **Memory is bounded, data is not.** Redis doesn't magically grow. Know your instance's memory limit, know your data's growth rate, and set TTLs accordingly.

5. **Document expected boundaries.** M6-2's K=5,000 failure is not a bug — it's a known limitation documented in the experiment report. Documenting it means future readers know the system's boundaries and don't spend days debugging a "failure" that's actually expected behavior.

---

***Next: [Cross-Experiment Findings](28-cross-experiment-findings.md) — four findings that span all experiments, and what to fix next.***
