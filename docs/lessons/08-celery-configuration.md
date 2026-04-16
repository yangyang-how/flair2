# 8. Celery Configuration Deep Dive

> Configuration is design. Every setting in `celery_app.py` encodes a decision about how the system should behave under pressure. This article explains what each knob does and what breaks when it's wrong.

## The full configuration

**File:** `backend/app/workers/celery_app.py`

```python
celery_app = Celery("flair2")
celery_app.conf.update(
    broker_url=settings.celery_broker_url,      # redis://localhost:6379/1
    result_backend=settings.redis_url,           # redis://localhost:6379/0
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
```

Nine settings. Let's take them one at a time.

## `broker_url` and `result_backend`

```python
broker_url=settings.celery_broker_url,    # Redis db=1
result_backend=settings.redis_url,         # Redis db=0
```

**Broker URL** points to Redis database 1. This is where Celery stores its message queues — the lists of tasks waiting to be processed.

**Result backend** points to Redis database 0. This is where Celery stores the return values of completed tasks (if any).

**Why different databases?** Redis databases (0-15) are isolated key namespaces within the same Redis instance. Using separate databases prevents Celery's internal keys (queue metadata, result keys, worker heartbeats) from colliding with the application's keys (run state, SSE streams, rate limiter counters).

This is a low-cost isolation technique. It doesn't provide performance isolation (both databases share the same Redis process and memory), but it prevents key naming collisions — which is the more immediate danger.

**What would break if they were the same database:** Celery uses keys like `celery-task-meta-{id}` and `_kombu.binding.*`. If the application happened to use a key with the same prefix, either Celery's internal state or the application's state would be corrupted. Separate databases eliminate the risk.

## `task_serializer`, `result_serializer`, `accept_content`

```python
task_serializer="json",
result_serializer="json",
accept_content=["json"],
```

These three settings work together:

- **`task_serializer="json"`:** when a task is enqueued, its arguments are serialized as JSON
- **`result_serializer="json"`:** when a task completes, its return value is serialized as JSON
- **`accept_content=["json"]`:** workers will only deserialize JSON messages; reject anything else

**Why this matters for security:** Celery's default serializer used to be `pickle`. Pickle deserialization can execute arbitrary Python code. If an attacker could push a message onto your Redis broker (not hard if Redis is exposed without auth), they could execute code on your workers. JSON-only prevents this attack vector entirely.

**The trade-off:** JSON can only serialize primitives (strings, numbers, booleans, lists, dicts). Task arguments and return values must be JSON-compatible. That's why Flair2's tasks receive string arguments (`video_json: str`) and deserialize them manually, rather than passing Pydantic objects directly.

## `task_track_started`

```python
task_track_started=True,
```

When a worker begins executing a task, it writes a "STARTED" status to the result backend. Without this setting, the only statuses are PENDING (not yet picked up) and SUCCESS/FAILURE (completed).

**Why it's useful:** monitoring. Without `task_track_started`, you can't distinguish between "the task is waiting in the queue" and "the task is actively running on a worker." With it, you can see which tasks are in-flight. This matters for debugging slow pipelines — you want to know if tasks are stuck in the queue or stuck mid-execution.

**The cost:** one extra Redis write per task (when the worker starts it). For Flair2's ~261 tasks per run, that's 261 extra Redis writes. Negligible.

## `task_acks_late`

```python
task_acks_late=True,
```

This is the most important setting. It controls when a task is "acknowledged" — removed from the broker's tracking.

**Default behavior (`acks_late=False`):** the worker acknowledges the task immediately after pulling it from the queue, *before* executing it. If the worker crashes mid-execution, the task is gone — it was already acknowledged.

**With `acks_late=True`:** the worker acknowledges the task only *after* it completes successfully. If the worker crashes mid-execution, the task is still on the broker and will be redelivered to another worker.

```
acks_late=False (default):
  Worker pulls task → ACK → starts work → crashes → TASK LOST

acks_late=True:
  Worker pulls task → starts work → crashes → NO ACK → TASK REDELIVERED
```

**Why Flair2 needs this:** a pipeline run involves 100+ tasks. If a worker crashes (out of memory, deployment rollout, network issue), the system should recover — not lose progress and fail silently. With `acks_late=True`, a crashed worker's tasks get re-executed by another worker.

**The catch — at-least-once delivery:** if a worker completes a task but crashes *before* sending the ACK, the broker thinks the task wasn't completed and redelivers it. The task runs twice. This means your tasks must be **idempotent** — running them twice should produce the same result as running them once.

In Flair2, this is handled by the SETNX cache pattern ([Article 18](18-setnx-and-idempotency.md)). If a task runs twice, the second execution finds the result already cached and returns it immediately.

**Design principle:** `acks_late=True` turns your system from "at-most-once" (task runs zero or one time) to "at-least-once" (task runs one or more times). At-least-once + idempotency gives you "effectively-exactly-once," which is what you actually want. This trade-off is fundamental to distributed systems — understand it deeply.

## `worker_prefetch_multiplier`

```python
worker_prefetch_multiplier=1,
```

This controls how many tasks a worker pre-fetches from the broker.

**Default behavior (`prefetch_multiplier=4`):** each worker pulls 4 tasks at a time from the queue. It starts executing one and keeps 3 in a local buffer. If the worker dies, those 3 buffered tasks are stuck until the worker's connection times out and the broker redelivers them.

**With `prefetch_multiplier=1`:** the worker pulls exactly one task at a time. It doesn't buffer extras. This has two consequences:

**Consequence 1 — Better fairness.** Imagine 100 S1 tasks are queued and 2 workers are running. With `prefetch_multiplier=4`, Worker A grabs tasks 1-4, Worker B grabs 5-8. If tasks 1-4 are fast and 5-8 are slow, Worker A finishes and grabs 9-12 while Worker B is still on task 5. The work distribution is uneven. With `prefetch_multiplier=1`, each worker grabs one task at a time. The faster worker grabs more tasks over time, naturally load-balancing.

**Consequence 2 — Faster recovery.** If a worker crashes with `prefetch_multiplier=4`, up to 3 buffered tasks are stuck until the broker detects the dead connection (usually 10-30 seconds). With `prefetch_multiplier=1`, at most 1 task is in-flight on the crashed worker.

**Consequence 3 — Slightly more broker overhead.** Each task requires a round-trip to the broker. With prefetching, you amortize that cost. For Flair2's workload (tasks take 2-5 seconds each), the broker round-trip (~1ms) is negligible.

**When to use higher prefetch:** when tasks are very fast (sub-second) and the broker round-trip becomes significant relative to task execution time. For Flair2's LLM calls (2-5 seconds each), `prefetch_multiplier=1` is the right choice.

## Settings NOT configured (and why they matter)

### `worker_concurrency`

Not set — defaults to the number of CPU cores. Controls how many tasks one worker process executes concurrently (using threads or child processes, depending on the pool type).

For Flair2's IO-bound tasks (waiting on Kimi API), the default is probably too low. Each task spends most of its time waiting for an HTTP response. More concurrency per worker would let one worker process handle more in-flight tasks. A value like `worker_concurrency=10` would better match the IO-bound workload.

### `task_time_limit` and `task_soft_time_limit`

Not set — no timeout. If a Kimi API call hangs forever, the task hangs forever, the worker slot is consumed forever. In production, you'd set `task_soft_time_limit=120` (soft kill after 2 minutes) and `task_time_limit=180` (hard kill after 3 minutes).

### `task_reject_on_worker_lost`

Not set — defaults to `False`. When a worker is killed (SIGKILL, OOM), the task stays in "STARTED" state indefinitely. With `task_reject_on_worker_lost=True`, the task is requeued. Combined with `acks_late=True`, this ensures crashed tasks are always recovered.

### `broker_connection_retry_on_startup`

Not set — defaults to `True` in Celery 5+. If the broker is down when the worker starts, it retries the connection. Important for ECS deployments where the worker might start before ElastiCache is ready.

## The interaction between settings

Settings don't exist in isolation. Here's how Flair2's configuration works as a system:

```
task_acks_late=True + worker_prefetch_multiplier=1:
  → Worker pulls one task, executes it, ACKs it, pulls the next.
  → If the worker crashes, exactly one task is lost (and redelivered).
  → Maximum fairness: each worker gets work one task at a time.

task_track_started=True + task_acks_late=True:
  → You can see three states: PENDING (queued), STARTED (in-flight), SUCCESS/FAILURE (done).
  → But: if a worker crashes after STARTED, the task shows as STARTED until redelivered.
  → There's a gap where the task looks "running" but isn't. Monitor worker heartbeats to detect this.

JSON serialization + acks_late:
  → Tasks are redeliverable AND readable in Redis.
  → You can inspect the broker queue, see what's pending, and manually intervene if needed.
```

## How to inspect the broker

If you have access to the Redis instance, you can see what's going on:

```bash
# How many tasks are in the queue?
redis-cli -n 1 LLEN celery

# What does the next task look like?
redis-cli -n 1 LRANGE celery 0 0

# How many active workers are there?
celery -A app.workers.celery_app inspect active
```

The M5-4 Locust experiment used `LLEN celery` (via ECS Exec) to measure queue depth in production. The result: 0-1 tasks in queue at K=100, confirming that workers were keeping up and the bottleneck was elsewhere (the Redis connection pool in the API layer, not worker throughput).

## What you should take from this

1. **`acks_late=True` is almost always what you want.** The cost (need for idempotency) is much lower than the risk (lost tasks on crash).

2. **`worker_prefetch_multiplier=1` for long tasks.** Prefetching helps only when tasks are fast relative to the broker round-trip. For multi-second tasks, always set it to 1.

3. **Missing settings are decisions too.** Not setting `task_time_limit` means "tasks can run forever." Not setting `worker_concurrency` means "use CPU count, even for IO-bound work." Review the defaults for every setting you don't configure.

4. **Security through serialization.** JSON-only prevents pickle deserialization attacks. This is a one-line security improvement that costs nothing.

5. **Settings interact.** `acks_late` changes the meaning of `task_track_started`. `prefetch_multiplier` changes the impact of worker crashes. Think about settings as a system, not individually.

---

***Next: [Worker Lifecycle and Failure](09-worker-lifecycle-and-failure.md) — what happens when a worker dies mid-task, and why idempotency isn't optional.***
