# 26. M5-4: Load Testing with Locust

> This is the experiment where the system broke. The most valuable experiment in the series — because the failure revealed a bottleneck that no amount of code review would have found.

## What Locust is

Locust is a Python-based load testing tool. You define user behavior in Python, specify how many concurrent users to simulate, and Locust sends requests and measures response metrics.

**File:** `backend/tests/experiments/locustfile.py`

```python
# Simplified:
class PipelineUser(HttpUser):
    wait_time = between(1, 3)

    @task
    def start_pipeline(self):
        self.client.post("/api/pipeline/start", json={...})

    @task
    def check_runs(self):
        self.client.get("/api/runs")
```

Each `PipelineUser` simulates a browser client that starts pipelines and checks run status. Locust spawns K of these users and reports latency distributions.

**Run command:**

```bash
locust -f locustfile.py --host=http://flair2-alb-xxxxx.us-west-2.elb.amazonaws.com \
    --users=500 --spawn-rate=50 --run-time=120s --headless
```

`--users=500`: simulate 500 concurrent users
`--spawn-rate=50`: add 50 users per second (ramp up over 10 seconds)
`--run-time=120s`: run for 2 minutes
`--headless`: no web UI, print results to console

## The results

| K | Median | p95 | p99 | RPS | Failures |
|---|--------|-----|-----|-----|----------|
| 10 | 35 ms | 51 ms | 190 ms | 4.81 | 0 |
| 50 | 35 ms | 59 ms | 100 ms | 48.24 | 0 |
| 100 | 34 ms | 61 ms | 140 ms | 47.96 | 0 |
| 500 (60s) | 69 ms | 2,900 ms | 4,200 ms | 175.89 | 4 |
| 500 (sustained) | 77 ms | 12,000 ms | 18,000 ms | 130.18 | 18 |

## Reading the data

### K=10 to K=100: stable zone

Median stays at 34-35ms. p95 stays under 100ms. p99 under 200ms. Zero failures. The system handles 100 concurrent users without any degradation.

**What this tells you:** at this scale, the system has headroom. Resources aren't contended. Every component is operating well within its limits.

### K=500, first 60 seconds: stress zone

Median jumps to 69ms (2x). p95 jumps to 2,900ms (47x). p99 hits 4,200ms (21x). 4 failures.

**The shape matters:** median doubled (moderate stress) but p95 jumped 47x (severe tail latency). This is the signature of a bounded resource approaching exhaustion — most requests proceed normally, but the unlucky ones that have to wait for the resource experience huge delays.

### K=500, sustained: breakdown zone

p95 hits 12,000ms. p99 hits 18,000ms. 18 failures. The system is degrading under sustained load.

**ECS auto-scaling kicked in:** a 3rd API task was added within ~2 minutes when CPU exceeded 60%. This helped somewhat — RPS was sustained at 130. But p95 didn't recover because the bottleneck wasn't CPU capacity.

## Finding the bottleneck

The standard debugging checklist for "system is slow":

| Resource | Status at K=500 | Bottleneck? |
|----------|----------------|-------------|
| API CPU | High (triggered auto-scaling) | Symptom, not cause |
| Worker CPU | 7.14% | No |
| Celery queue depth | 0-1 tasks | No |
| Redis server | Sub-millisecond response | No |
| Network | Normal | No |
| Redis connection pool | ??? (not instrumented) | **Yes** |

**Worker CPU at 7.14%** is the key data point. Workers are IO-bound — they're waiting for Kimi API responses, not computing. Even at K=500, workers have massive spare capacity. This rules out "not enough workers" as the explanation.

**Queue depth at 0-1** rules out "tasks are piling up faster than workers can process them." Workers are keeping up.

**Redis server** was fast — individual operations completed in sub-millisecond time. The Redis instance wasn't overloaded.

**The remaining explanation:** the API tasks couldn't get connections from their Redis connection pool. Each SSE connection holds a Redis connection for ~5 seconds (blocking XREAD). With 500 concurrent SSE connections and a small pool, most connections were waiting for a pool slot.

This is the connection pool bottleneck described in [Article 19](19-connection-pool-bottleneck.md).

## The auto-scaling response

At K=500, CPU auto-scaling triggered:
1. API CPU exceeded 60% target
2. ECS added a 3rd API task (~2 minutes delay)
3. Load was redistributed across 3 tasks
4. But each task still had the same small connection pool

**Adding a 3rd task helped with CPU** (more request-handling capacity) but **didn't help with connection pools** (each task brought its own small pool, and 500/3 ≈ 167 concurrent SSE connections per task still exceeded the per-task pool size).

**Lesson:** auto-scaling fixes CPU bottlenecks, not connection pool bottlenecks. If the bottleneck is internal to each task (pool size, thread count, file descriptor limit), adding more tasks multiplies the problem rather than solving it.

## The live queue depth measurement

ECS Exec (enabled by PRs #129/#130) was used to measure queue depth from inside a running worker task:

```bash
# From inside the ECS task:
redis-cli -h <elasticache-endpoint> LLEN celery
# Result: 0 or 1
```

This confirmed that the Worker tier wasn't the bottleneck. If `LLEN celery` had returned 500, it would mean tasks were piling up faster than workers could process them — a sign that more workers were needed. The result of 0-1 means workers were keeping up easily.

**This measurement was only possible because of ECS Exec.** Without it, you'd need to deploy a monitoring sidecar or publish custom metrics. The ECS Exec setup took 2 PRs (#129 for the feature, #130 for the IAM permission fix) — a small investment that paid off immediately during the experiment.

## What the inflection point means

K=100 → K=500 is a **phase transition**. Below K=100, the system operates in a stable regime. Above K=500, a bounded resource (connection pool) is exhausted and behavior changes qualitatively.

**Phase transitions in distributed systems are common:**
- Below the inflection: everything looks fine, metrics are flat
- At the inflection: tail latency spikes, failures appear, but median looks okay
- Above the inflection: cascading failure, resource contention spreads to other components

**Why you test beyond your expected operating range:** if you expect K=100 in production and only test K=100, you don't know where the inflection point is. When a marketing campaign drives K=200, you discover the inflection point in production — at 3 AM, with users complaining.

Test to at least 5x your expected load. Know where it breaks. Plan for it.

## Locust as a tool

### Advantages
- **Python-based:** user behaviors are just Python classes. Familiar language, easy to customize.
- **Distributed testing:** Locust can run on multiple machines for higher concurrency.
- **Built-in statistics:** p50, p95, p99, RPS, failure count — the metrics you need.
- **Web UI:** real-time charts during the test (or `--headless` for CI).

### Alternatives
- **k6:** JavaScript-based, from Grafana Labs. Better performance (Go runtime), more modern.
- **JMeter:** Java-based, GUI-heavy. Powerful but complex.
- **wrk/hey:** command-line tools for simple HTTP benchmarking. No user scenarios.
- **Gatling:** Scala-based, strong simulation capabilities.

**When to use Locust:** when your team writes Python and your test scenarios are complex (multi-step workflows, conditional behavior, data-dependent requests).

## What you should take from this

1. **Tail latency reveals what median hides.** If you only reported median (77ms), K=500 looks fine. p95 (12s) and p99 (18s) tell the truth.

2. **Measure every resource, especially the ones you don't think matter.** Worker CPU being at 7.14% was the most important measurement — because it proved the bottleneck was elsewhere.

3. **Phase transitions are cliff-edges.** Systems don't degrade linearly. They work fine, then they hit a wall. Find the wall in testing, not in production.

4. **Auto-scaling helps only if the bottleneck is what you're scaling.** Adding CPU capacity when the bottleneck is a connection pool is like adding more lanes to a highway when the bottleneck is a single toll booth.

5. **Live debugging (ECS Exec) is invaluable.** The `LLEN celery` measurement from inside the running container provided a critical data point that no external metric could provide.

---

***Next: [M6: ElastiCache Under Real Concurrency](27-m6-elasticache.md) — what happens when you move from fakeredis to real Redis.***
