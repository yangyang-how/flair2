# 9. Worker Lifecycle and Failure

> The defining question of distributed systems: what happens when something crashes? A system's reliability isn't measured by how it behaves when everything works — it's measured by how it behaves when things fail.

## A worker's life

A Celery worker process runs a simple loop:

```
while True:
    message = broker.pull_task()       # BLPOP on Redis list
    task_fn = deserialize(message)     # JSON → function + args
    status = "STARTED"                 # task_track_started=True
    try:
        result = task_fn(*args)        # run the task
        status = "SUCCESS"
        broker.ack(message)            # acks_late: ACK after completion
    except Exception as e:
        status = "FAILURE"
        broker.ack(message)            # failed, but acknowledged
        report_error(e)
```

The nuances are in the edge cases.

## Failure mode 1: Task raises an exception

The task function throws an error. Maybe Kimi returned unparseable JSON, or the rate limiter timed out, or a Redis connection failed.

**What happens:**
1. The exception is caught by Celery's task executor
2. The task is marked as FAILURE in the result backend
3. The task IS acknowledged (removed from the queue) — even with `acks_late=True`
4. The exception is logged

**In Flair2:** the task's error handler catches `ProviderError` and `StageError` and calls `orchestrator.on_failure()`, which marks the entire run as failed and publishes a `pipeline_error` event to the SSE stream. The user sees "Pipeline failed at S1: rate limit exceeded" in real time.

**Design choice:** Flair2 does NOT retry on exception by default. An LLM error that produced unparseable output is likely to produce unparseable output again. Instead, the run fails and the user can start a new one. This is a deliberate choice — automatic retry is appropriate for transient errors (network blip), not for semantic errors (bad LLM output).

If you wanted automatic retry, Celery supports it:

```python
@celery_app.task(
    autoretry_for=(ProviderError,),
    retry_backoff=True,
    max_retries=3,
)
def s1_analyze_task(run_id, video_json):
    ...
```

Flair2 doesn't use this, but the provider classes implement their own retry logic internally (3 retries with exponential backoff for rate limits and JSON parse failures — see `providers/kimi.py`).

## Failure mode 2: Worker crashes mid-task

The worker process is killed — OOM killer, SIGKILL from ECS, deployment rollout, hardware failure.

**What happens (with `acks_late=True`):**
1. The worker disappears. The TCP connection to Redis drops.
2. Redis detects the dead connection (after a timeout, typically 30-60 seconds).
3. The unacknowledged message is returned to the queue.
4. Another worker picks it up and executes it.

**What happens (with `acks_late=False`, the default):**
1. The worker disappears.
2. The task was already acknowledged. It's gone.
3. Nobody knows it needs to re-run.
4. The pipeline hangs forever, waiting for a completion that will never come.

This is why `acks_late=True` exists, and why Flair2 uses it.

**The gap:** between the crash and Redis detecting the dead connection, the task appears to be "in flight" — `task_track_started=True` shows it as STARTED. There's no worker executing it, but nobody knows that yet. This is the **visibility timeout** problem, and it exists in every distributed queue (SQS calls it "visibility timeout" explicitly).

## Failure mode 3: Worker completes task, crashes before ACK

This is the trickiest case.

```
Worker:  runs task → SUCCESS → about to ACK → crashes
Broker:  never got the ACK → redelivers task to another worker
Result:  task runs twice
```

With `acks_late=True`, this scenario is guaranteed to happen eventually. The task executes successfully, the result is stored in Redis, but the ACK never reaches the broker. The broker redelivers. A second worker runs the same task again.

**This is at-least-once delivery.** The task runs one or more times. You cannot prevent this with Celery — it's a fundamental property of distributed message queues. The options are:

1. **At-most-once** (`acks_late=False`): task runs zero or one time. You might lose tasks.
2. **At-least-once** (`acks_late=True`): task runs one or more times. You might run duplicates.
3. **Exactly-once**: doesn't exist in practice across process boundaries.

Flair2 chooses at-least-once, and handles duplicates through **idempotency**.

## Idempotency: the key concept

An operation is **idempotent** if performing it multiple times has the same effect as performing it once.

```
Idempotent:     SET user.name = "Sam"           (same result if run 10 times)
NOT idempotent: INCR counter                     (different result each time)
```

Flair2's task design is structured to be idempotent:

### Stage results: overwrite, not append

S1 results are stored at `s1_result:{run_id}:{video_id}`. If the task runs twice, the second execution overwrites the first with (presumably) the same or equivalent result. No duplicate data.

### Counters: the dangerous part

The orchestrator uses `INCR run:{id}:s1:done` to count completed S1 tasks. If a task runs twice, the counter gets incremented twice. If there are 100 videos, the counter might reach 101. This would cause `on_s1_complete` to see `done >= num_videos` on the 100th AND 101st increment, potentially triggering S2 twice.

**In practice, this is handled by the orchestrator's transition logic.** `_transition_s2` dispatches a single S2 task. If it's called twice, two S2 tasks are dispatched — but S2 is idempotent (it reads all S1 results and aggregates them; doing it twice produces the same output).

This isn't perfect. A production system would use a Redis Lua script for the atomic "increment and check" operation, or use a flag (`SET run:{id}:s2:started NX`) to ensure the transition fires exactly once. Flair2 accepts the small risk of double-dispatching a reduce stage, since reduce stages are idempotent.

### SETNX caching: natural idempotency

The `cache_get_or_compute` method in `infra/redis_client.py` uses SETNX (SET if Not eXists) to ensure only one worker computes a result for a given cache key. If a task runs twice, the second execution finds the cached result and returns immediately. This is covered in detail in [Article 18](18-setnx-and-idempotency.md).

## Failure mode 4: Broker goes down

Redis is the broker. If Redis goes down:

- No new tasks can be enqueued (producers can't `LPUSH`)
- No tasks can be consumed (workers can't `BLPOP`)
- No state can be read or written
- SSE streams stop flowing

The entire system halts.

**Why this is acceptable for Flair2:** it's a prototype and course project running on a single `cache.t3.micro` ElastiCache instance. The risk of Redis failure is accepted.

**How to mitigate in production:**
- **Redis Sentinel** for automatic failover
- **Redis Cluster** for horizontal scaling
- **Separate broker and state store** — use RabbitMQ or SQS for the broker (built for messaging), Redis for state (built for data). If the broker dies, state is preserved and vice versa.
- **Circuit breaker pattern** — if Redis is unreachable, fail requests fast instead of hanging

## Failure mode 5: Task runs forever

A Kimi API call hangs. The task blocks indefinitely. The worker slot is consumed.

**Flair2's current behavior:** no timeout. The task blocks forever. The worker can't process other tasks in that slot. If all worker slots are consumed by hanging tasks, the pipeline freezes.

**The fix:** `task_time_limit` and `task_soft_time_limit`.

```python
# Not in Flair2, but should be:
task_soft_time_limit=120,  # SoftTimeLimitExceeded after 2 min
task_time_limit=180,       # SIGKILL after 3 min
```

`task_soft_time_limit` raises a `SoftTimeLimitExceeded` exception inside the task, giving it a chance to clean up (mark the run as failed, close connections). `task_time_limit` sends SIGKILL — unconditional process death. The gap between soft and hard limits is the cleanup window.

## The crash recovery mechanism

Flair2 has explicit crash recovery for the most expensive stage (S4 — persona voting):

**File:** `pipeline/orchestrator.py` — `recover()`

```python
async def recover(self, run_id: str) -> None:
    config = await self._load_config(run_id)
    s4_done = await self._r.read_checkpoint(run_id, "s4") or 0

    for i in range(s4_done, config.num_personas):
        s4_vote_task.delay(run_id, f"persona_{i}")
```

Each S4 completion writes a checkpoint (`checkpoint:{run_id}:s4 = N`). If the system crashes mid-S4 (after 60 of 100 personas have voted), the recovery reads the checkpoint and dispatches only the remaining 40 tasks.

**Why only S4?** Because S4 is the most expensive stage — 100 concurrent LLM calls, each costing time and money. S1 is also a fan-out stage, but it's first — there's no expensive prior work to lose. S6 fans out only 10 tasks — cheap to re-run. S4 is the sweet spot where checkpoint cost (one Redis write per completion) is justified by recovery savings (up to 99 skipped LLM calls).

The M5-2 experiment tested this: checkpointing saved 47-73% of API calls depending on crash timing. That's the empirical evidence that the mechanism is worth its cost.

## The delivery guarantee spectrum

This is the framework that ties all failure modes together:

```
At-most-once     │     At-least-once          │     Exactly-once
(lose tasks)     │     (duplicate tasks)       │     (impossible in practice)
                 │                             │
acks_late=False  │     acks_late=True          │     acks_late=True
                 │                             │     + idempotency
                 │                             │     + deduplication
                 │                             │
Simpler          │     Moderate complexity     │     Highest complexity
Acceptable for   │     Standard for most       │     Required for
non-critical     │     production systems      │     financial transactions
work             │                             │
```

Flair2 sits in the middle: at-least-once delivery with partial idempotency. For an LLM pipeline where a duplicate API call produces (roughly) the same result, this is the right trade-off. For a payment processing system, you'd need stronger guarantees.

## What you should take from this

1. **Plan for crashes, not uptime.** Every component will crash eventually. The question isn't "what if it crashes?" but "when it crashes, what's the blast radius?"

2. **`acks_late=True` trades duplicates for durability.** Almost always the right trade-off. Duplicates can be handled with idempotency; lost tasks can't be recovered.

3. **Idempotency is a design requirement, not an optimization.** If you use at-least-once delivery, your tasks MUST be idempotent. Design for it from the start — retrofitting idempotency is painful.

4. **Checkpoints are cheap insurance for expensive work.** One Redis write per S4 completion costs microseconds. Rerunning 60 LLM calls costs minutes and money. The math is obvious — but teams often skip checkpointing because "it probably won't crash." It will.

5. **Exactly-once delivery is a lie.** Systems that claim exactly-once are actually implementing at-least-once + deduplication. The deduplication can be very good (Kafka's transactional writes), but it's always at-least-once underneath.

---

***Next: [The Orchestrator State Machine](10-the-orchestrator.md) — the single writer that controls all stage transitions.***
