# 28. Cross-Experiment Findings

> Individual experiments answer individual questions. Cross-experiment findings emerge when you look at all the data together and ask: "what patterns span multiple experiments?" These findings are the most valuable — they reveal systemic properties, not component-level behaviors.

## Finding 1: Redis connection pool is the system-wide bottleneck at scale

**Evidence:**
- M5-4: API p99 = 18,000ms at K=500. CPU and queue depth were fine.
- M6-2: SETNX tests failed at K=5,000. Redis server was fine.

**Diagnosis:** both failures trace to the same root cause — too many concurrent coroutines competing for a limited pool of TCP connections to Redis. The pool is the invisible choke point.

**Why it's system-wide:** every component uses Redis — the API (for SSE streaming), the workers (for state and rate limiting), the orchestrator (for counters and events). They all share the same pool (or pools with the same default size). When any one of these saturates the pool, all of them are affected.

**The fix (not yet implemented):**
1. Increase `max_connections` on the Redis client (sizing to match expected concurrency)
2. Separate pools for SSE (long-held) and API requests (short-lived)
3. Add connection pool metrics to CloudWatch for monitoring
4. Set connection acquisition timeouts so failures are fast and visible

**The lesson:** the most dangerous bottlenecks are the ones that don't appear on standard dashboards. CPU, memory, network — all visible. Connection pool utilization — invisible without custom instrumentation.

## Finding 2: CPU is the wrong auto-scaling metric for Workers

**Evidence:**
- M5-4: Worker CPU peaked at 7.14% at K=500. Workers were idle while the system was overloaded.
- ECS Worker auto-scaling target: CPU > 70%. Will never trigger.

**Diagnosis:** Workers are IO-bound. They spend 99.7% of their time waiting for LLM API responses. CPU doesn't reflect their workload.

**What the right metric is:** Celery queue depth (`LLEN celery` in Redis). If tasks are piling up in the queue, workers aren't keeping up — add more. If the queue is empty, workers are adequate.

**Why this matters beyond Flair2:** any system with IO-bound workers (API clients, database readers, network-heavy tasks) will have this same problem. CPU scaling is appropriate for CPU-bound work (computation, rendering, compression). For IO-bound work, scale on queue depth, active connections, or request latency.

**The broader principle:** the right scaling metric is a proxy for user-visible impact. CPU utilization is a proxy for "the machine is busy." Queue depth is a proxy for "users are waiting." The second is almost always more relevant.

## Finding 3: fakeredis hides real distributed failure modes

**Evidence:**
- M5 (fakeredis): all 17 tests passed. SETNX, rate limiting, and backpressure all worked perfectly.
- M6 (ElastiCache): 27/29 tests passed. 2 failures at K=5,000 due to connection pool exhaustion.

**Diagnosis:** fakeredis is a single-threaded in-process simulator. It has no TCP connections, no connection pools, no network latency, and no memory limits. Tests that pass on fakeredis prove logic correctness but not system correctness.

**The failure that's invisible in fakes:** SETNX atomicity trivially holds in fakeredis because there's no real concurrency — all operations are serialized by Python's GIL. The interesting question isn't "is SETNX atomic?" (always yes, by Redis spec) but "can all clients reach Redis to issue their SETNX?" (depends on connection pool, network, and server capacity).

**When to use fakes vs real infrastructure:**

| Use fakes when | Use real infra when |
|----------------|-------------------|
| Testing business logic | Testing scalability |
| Fast iteration on experiment design | Validating production behavior |
| CI (every commit) | CD (post-deployment) |
| Known failure modes | Discovering unknown failure modes |

**The lesson:** fakes test what you expect. Real infrastructure reveals what you didn't expect. You need both.

## Finding 4: Auto-scaling works but needs tuning

**Evidence:**
- M5-4: ECS auto-scaling correctly detected CPU overload at K=500 and added a 3rd API task within ~2 minutes.
- But: p95 was still 12,000ms after scaling, because the bottleneck wasn't CPU.
- Worker auto-scaling never triggered (CPU too low).

**Diagnosis:** auto-scaling responded correctly to its configured metric. The problem is the metric doesn't represent the bottleneck.

**What tuning means:**
1. **API:** scale on connection count or custom latency metrics, not just CPU
2. **Worker:** scale on queue depth, not CPU
3. **Cooldown periods:** the 2-minute scaling delay at K=500 meant the system was degraded for 2 minutes before help arrived. Shorter cooldowns react faster but risk thrashing.
4. **Scaling step size:** adding 1 task at a time is conservative. Adding 2-3 at once reacts faster but may overshoot.

**The broader principle:** auto-scaling is a control system. It has a sensor (metric), a target (threshold), an actuator (scaling action), and a feedback loop (cooldown). If the sensor is measuring the wrong thing, the entire loop is useless — it will react perfectly to the wrong signal.

## The architecture, validated

Taking all experiments together, here's what's confirmed about Flair2's architecture:

| Design decision | Validated by | Verdict |
|----------------|-------------|---------|
| Centralized rate limiting | M5-1 | Works. 0% error rate at K=10 vs 90% without. |
| Checkpoint recovery | M5-2 | Works. Saves 30-73% of LLM calls. |
| SETNX caching | M5-3 | Works. Fixed LLM call count regardless of K. |
| Two-tier architecture (API + Worker) | M5-4 | Works, but pool sizing needed at K>100. |
| Redis as broker + state | M6 | Works up to K≈1,000. Connection pool is the ceiling. |
| Single-writer orchestrator | All | Works. No interleaving bugs observed in any experiment. |

## What to fix next

If Flair2 were going to production, the priority list is:

### Priority 1: Connection pool sizing
- Add `max_connections=200` to the Redis client
- Separate pools for SSE and API
- Add pool metrics to CloudWatch
- **Expected impact:** raise the K threshold from ~500 to ~2,000+

### Priority 2: Worker auto-scaling metric
- Publish Celery queue depth to CloudWatch
- Scale Workers on queue depth, not CPU
- **Expected impact:** Workers actually scale when they should

### Priority 3: Rate limiter atomicity
- Replace INCR + EXPIRE with a Lua script
- Eliminates the crash-window race condition
- **Expected impact:** rare edge case fixed; more important as scale increases

### Priority 4: Task timeouts
- Add `task_soft_time_limit=120` and `task_time_limit=180` to Celery
- Prevents hanging tasks from consuming worker slots indefinitely
- **Expected impact:** resilience under LLM API outages

### Priority 5: DynamoDB integration
- Wire DynamoDB into the hot path for persistent storage
- Results survive beyond Redis TTL
- **Expected impact:** run history available for analytics, not just 24 hours

## The meta-lesson

The experiments taught something more fundamental than any individual finding: **you don't understand your system until you've broken it.**

Before M5-4, the team believed the system was bottlenecked by LLM rate limits (because that's the most obviously scarce resource). The load test proved the real bottleneck was a Redis connection pool that nobody was monitoring.

Before M6-2, the team had confidence from M5-3 that SETNX caching worked at any scale (all 17 fakeredis tests passed). M6-2 showed that the client-side infrastructure breaks at K=5,000.

**The pattern:** systems fail at their boundaries, not at their centers. The Redis server was never the problem. The LLM API was never the problem. The connection pool — the boundary between the application and Redis — was the problem. Boundaries are where different systems meet, and they're where assumptions break.

**How to apply this:**
1. **Test boundaries, not just components.** The connection pool is at the boundary between your code and Redis. The rate limiter is at the boundary between your code and the LLM API. The ALB is at the boundary between the internet and your code. Boundaries are where failures hide.
2. **Instrument boundaries.** Add metrics at every boundary: pool utilization, queue depth, upstream latency. These are the signals that predict failures before they happen.
3. **Break your system intentionally.** Failure injection (M5-2), load testing (M5-4), and scale testing (M6-2) are cheaper than production incidents. Budget time for them.

## Where to go from here

If you've read all 28 articles, you now understand:
- How a distributed AI pipeline is structured and why
- The task queue pattern, MapReduce, and SSE streaming
- Redis as a multi-role infrastructure component
- Connection pooling, rate limiting, and caching
- Auto-scaling and its limitations
- How to design and interpret distributed systems experiments

The next step is to build something. Not another tutorial project — a real system with real constraints. Pick a problem that's naturally distributed (fan-out, coordination, shared resources) and design a solution. When it breaks — and it will — you'll recognize the failure modes because you've seen them here.

The goal was never to memorize Flair2's architecture. It was to internalize the thinking: **what problem am I solving? What are the forces? What would break this design? Where are the boundaries?** Those questions apply to every system you'll ever build.

---

*This concludes the 28-article series on Flair2's architecture and distributed systems design. The codebase is at [github.com/yangyang-how/flair2](https://github.com/yangyang-how/flair2).*
