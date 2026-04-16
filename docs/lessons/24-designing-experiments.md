# 24. Designing Distributed Systems Experiments

> Experiments are how you turn "I think this works" into "I know this works under these conditions." This article teaches the experimental method applied to distributed systems — hypotheses, variables, controls, and interpretation.

## Why experiment, not just test

Tests verify correctness: "does this function return the right output?" Experiments answer questions: "how does the system behave under load?" "at what concurrency level does it break?" "how much does caching save?"

The distinction matters because distributed systems have **emergent behavior** — properties that only appear at scale, under concurrency, or when components fail. You can't unit test your way to understanding these. You need experiments.

Flair2 ran four experiments across two milestones:
- **M5-1:** Backpressure — how the rate limiter affects multi-tenant fairness
- **M5-2:** Failure recovery — what checkpointing saves when a worker crashes
- **M5-3:** Cache concurrency — how SETNX caching scales with K concurrent users
- **M5-4:** API load test — where the system breaks under K=10 to K=500 concurrent users
- **M6-1/2/3:** ElastiCache — real Redis vs fakeredis for latency, atomicity, and memory

Each experiment follows the same structure. Learning this structure lets you design experiments for any system.

## The experimental method for systems

### Step 1: Ask a question

Start with a specific, falsifiable question. Not "does the system work?" but:

- "Does the rate limiter prevent LLM errors under K=10 concurrent users?" (M5-1)
- "How many LLM calls does checkpointing save when a worker crashes at 50% completion?" (M5-2)
- "Is SETNX atomicity guaranteed under K=5000 concurrent connections on real Redis?" (M6-2)

**The question should be answerable with data.** "Is the system fast?" is not a question — "fast" isn't measurable. "Is p99 latency under 200ms at K=100?" is a question.

### Step 2: Formulate a hypothesis

State what you expect to happen and why:

- **M5-1 hypothesis:** "The rate limiter will keep LLM error rate at 0% regardless of K, because the token bucket enforces the per-minute limit centrally."
- **M5-4 hypothesis:** "API latency will be stable up to some K, then degrade rapidly. The inflection point reveals the system's true capacity."

**Why hypotheses matter:** they force you to predict before measuring. If the result matches your prediction, your mental model is confirmed. If it doesn't, your mental model is wrong — and that's the interesting case.

### Step 3: Identify variables

**Independent variable:** what you change. In most Flair2 experiments, this is **K** (number of concurrent users/connections).

**Dependent variable:** what you measure. Latency (p50, p95, p99), error rate, LLM call count, CPU utilization, queue depth, memory usage.

**Control variables:** what you hold constant. Same Redis instance, same dataset, same API key, same rate limit, same deployment configuration. If you change two things at once, you can't tell which caused the effect.

### Step 4: Choose measurement points

Don't just test K=10 and K=1000. Test enough points to see the shape:

```
K = 10, 50, 100, 500, 1000
```

M5-4 tested K = 10, 50, 100, 500. The results showed:
- K=10-100: stable (p99 < 200ms)
- K=500: inflection point (p99 = 18,000ms)

The shape tells you more than any single point. K=500 is where something breaks. That's the number to investigate.

### Step 5: Control for noise

Distributed systems are noisy. Network latency varies. LLM response times vary. GC pauses happen. To get reliable results:

- **Run multiple trials** and report statistics (median, p95, p99), not single values
- **Warm up** before measuring (first few requests may be slow due to connection establishment, JIT compilation, etc.)
- **Use consistent infrastructure** (same instance type, same region, same time of day)
- **Isolate the system under test** (don't run other workloads on the same Redis instance during experiments)

M5-4 used Locust's built-in statistics (p50, p95, p99, RPS, failure count) aggregated over the test duration. Multiple concurrent users provide natural statistical sampling.

### Step 6: Interpret results

**Look for inflection points.** Where does behavior change qualitatively? M5-4's inflection at K=500 is a phase transition — below it, the system is stable; above it, tail latency explodes.

**Look for surprises.** M5-4's biggest surprise: Worker CPU at 7.14% during the highest load. The system was dying, but Workers were idle. This tells you the bottleneck is NOT the Workers — it's somewhere else in the chain.

**Look for confirmation across experiments.** M5-4 (API p99 = 18s at K=500) and M6-2 (SETNX failures at K=5000) both point to Redis connection pool exhaustion. One experiment is evidence. Two experiments with the same root cause is a pattern.

**Be honest about what you didn't measure.** M5-4 didn't measure connection pool utilization directly (no metric was published). The diagnosis was inferred from the pattern (high latency, low CPU, empty queue). A direct measurement would be stronger evidence.

## Experiment design patterns

### Pattern 1: Scaling test

**Question:** how does metric Y change as variable X increases?
**Design:** hold everything constant, vary X, measure Y at each point.
**Example:** M5-4 — vary K (concurrent users), measure latency.

This is the most common experiment type. The result is a curve (Y vs X) that reveals the system's scaling characteristics — linear, sublinear, or step-function (cliff).

### Pattern 2: A/B comparison

**Question:** does mechanism M improve metric Y?
**Design:** run the same workload with and without M, compare results.
**Example:** M5-1 — run with and without the rate limiter, compare error rates.

The control (without M) tells you what the baseline behavior is. The treatment (with M) tells you what the mechanism achieves. The difference is the mechanism's impact.

### Pattern 3: Failure injection

**Question:** what happens when component C fails at time T?
**Design:** run normally, inject failure at a specific point, observe recovery.
**Example:** M5-2 — kill a worker mid-S4, measure how many tasks are recovered from checkpoint.

Failure injection is the most valuable and most underused experiment type. It answers the question "is the system actually resilient, or just lucky?" Most teams never test their recovery paths until they need them in production.

### Pattern 4: Local vs real

**Question:** does the behavior observed in local testing hold in the real deployment?
**Design:** run the same test against fakeredis and against ElastiCache, compare results.
**Example:** M6 — all three experiments compare local behavior with ElastiCache behavior.

This reveals **hidden assumptions** in your testing infrastructure. M6-2 proved that SETNX atomicity is trivial in fakeredis (single-threaded, no real concurrency) but reveals connection pool limits with real Redis. The unit test was giving false confidence.

## Common pitfalls

### Pitfall 1: Measuring the wrong thing

M5-4 initially focused on API latency. Worker CPU was measured as a secondary metric. The Worker CPU result (7.14%) was the most important finding — it proved the Workers weren't the bottleneck, redirecting investigation to the API layer and Redis connection pool.

**Lesson:** measure everything you can, not just the thing you think matters. The most valuable data is often in the metric you almost didn't collect.

### Pitfall 2: Not enough points

If M5-4 had only tested K=10 and K=100, it would have concluded "system works perfectly at any scale." The K=500 test revealed the cliff. Always test beyond your expected operating range.

### Pitfall 3: Ignoring tail latency

If M5-4 had only reported median latency, K=500 would look okay (77ms median). p95 (12,000ms) and p99 (18,000ms) tell the real story — 5% of users wait 12+ seconds. **Report percentiles, not averages.** Averages hide the worst-case experience.

### Pitfall 4: Confusing correlation with causation

M5-4 showed that API latency increased at K=500. Worker CPU was at 7%. Queue depth was 0-1. The diagnosis (connection pool exhaustion) is an inference, not a direct observation. The pool itself wasn't instrumented. A different explanation could fit the same data.

**When to accept inference vs demand proof:** in a course project, inference from multiple data points is sufficient. In production, you'd instrument the pool and measure directly.

## What you should take from this

1. **Start with a question, not a tool.** Don't start with "let's run Locust." Start with "at what concurrency does the system break?" Then choose the tool that answers the question.

2. **Hypothesize before measuring.** Predictions make you learn faster — either you're right (confirm your model) or you're wrong (discover a gap in your model).

3. **Test beyond your operating range.** If you expect K=100 in production, test K=500 and K=1000. The failure mode at 5x your expected load is the one that will wake you up at 3 AM when a marketing campaign goes viral.

4. **Report percentiles, not averages.** p50 (median) tells you the typical experience. p95 and p99 tell you the worst-case experience. Both matter.

5. **Failure injection is the most valuable experiment.** It's the only way to verify that recovery mechanisms work. Test them in controlled conditions, not in production incidents.

---

***Next: [M5: Pipeline Resilience](25-m5-pipeline-resilience.md) — the three local experiments and what each proved.***
