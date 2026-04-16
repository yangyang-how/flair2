# 10. The Orchestrator State Machine

> The orchestrator is the brain of the pipeline — the single writer that decides when each stage starts, tracks progress, and transitions the system through its states. Understanding it means understanding how distributed coordination works without locks.

## The single writer principle

Open `backend/app/pipeline/orchestrator.py`. The first docstring tells you everything:

```
Single writer to the SSE stream (sse:{run_id}) and all stage/status keys.
Workers call on_sX_complete() callbacks; the orchestrator decides when to
transition and dispatches the next batch of tasks.
```

**Single writer** means: only the orchestrator modifies `run:{id}:status`, `run:{id}:stage`, and `sse:{id}`. Workers never write to these keys directly. Workers report completion through callbacks (`on_s1_complete`, `on_s4_complete`, etc.), and the orchestrator — running inside the worker's process — decides what to do.

This eliminates a whole class of bugs. Imagine two workers both completing S1 tasks simultaneously. Without single-writer discipline, both might try to set `run:{id}:stage = "S2_REDUCE"` and both might dispatch the S2 task — resulting in two S2 runs. With single-writer discipline, the `INCR` counter is atomic, and only the worker that increments it to exactly `num_videos` triggers the transition.

**Where you'll see this pattern again:**
- **Raft consensus:** one leader handles all writes; followers replicate
- **Event sourcing:** one writer appends to the log; readers derive state
- **Database write-ahead logs:** one writer thread appends; readers are lock-free
- **Single-threaded event loops (Node.js, Redis):** one thread handles all mutations; no locks needed

The principle is the same everywhere: **mutation through one writer is simpler and safer than mutation through many writers with coordination.** The cost is that all mutations are serialized through one path. For Flair2's workload (transitions happen ~10 times per run), this is zero cost.

## The state machine

The pipeline has a fixed sequence of states:

```
S1_MAP → S2_REDUCE → S3_SEQUENTIAL → S4_MAP → S5 → S6_MAP → DONE
                                                              │
                                               (any stage) → FAILED
```

The orchestrator tracks the current state in `run:{id}:stage`. Transitions happen only through the `_transition_s*` methods. There is no way to skip a stage, go backwards, or branch.

This is a **finite state machine (FSM)**: a fixed set of states, a fixed set of transitions, and a deterministic rule for each transition. FSMs are one of the most useful concepts in computer science — any time you have a sequential process with well-defined steps, an FSM is the right model.

## Initialization: `start()`

```python
async def start(self, run_id, config, videos):
    await self._r.set(f"run:{run_id}:config", config.model_dump_json())
    await self._r.set(f"run:{run_id}:status", "running")
    await self._r.set(f"run:{run_id}:stage", "S1_MAP")

    for key in [f"run:{run_id}:s1:done", f"run:{run_id}:s4:done", f"run:{run_id}:s6:done"]:
        await self._r.delete(key)
        await self._r.set(key, "0")

    await self._xadd_event(run_id, "pipeline_started", {...})
    await self._xadd_event(run_id, "stage_started", {"stage": "S1_MAP", "total_items": len(videos)})

    for video in videos:
        s1_analyze_task.delay(run_id, video.model_dump_json())
```

**Counter initialization:** notice the `delete` then `set("0")` pattern. Why not just `set("0")`? Because if a previous run with the same ID partially completed (failed, then retried), the counter might have a stale value. `delete` first ensures a clean start. This is defensive programming — handle the case where state from a previous attempt exists.

**Task dispatch:** the `for` loop dispatches one Celery task per video. Each `.delay()` pushes a message onto the Redis broker queue. The orchestrator doesn't wait — it fires all 100 tasks and returns.

## The completion callback pattern

Each fan-out stage (S1, S4, S6) uses the same pattern:

```python
async def on_s1_complete(self, run_id, video_id):
    done = await self._r.incr(f"run:{run_id}:s1:done")
    config = await self._load_config(run_id)

    await self._xadd_event(run_id, "s1_progress", {
        "video_id": video_id,
        "completed": done,
        "total": config.num_videos,
    })

    if done >= config.num_videos:
        await self._transition_s2(run_id)
```

Let's break down why each line exists:

**`INCR` is atomic.** Redis guarantees that concurrent `INCR` operations on the same key are serialized. If two workers call `on_s1_complete` at exactly the same time, one gets `done=99`, the other gets `done=100`. They never both get `100`. This is the coordination mechanism — no locks, no mutexes, just an atomic counter.

**`config.num_videos` is the threshold.** The orchestrator reloads the config from Redis rather than storing it in memory. This is because the orchestrator runs inside worker processes — different `on_s1_complete` calls might run on different machines, with no shared memory. Redis is the only shared state.

**`done >= config.num_videos` rather than `done == config.num_videos`.** Why `>=`? Because of the duplicate delivery scenario from [Article 9](09-worker-lifecycle-and-failure.md). If a task runs twice, the counter could exceed `num_videos`. Using `>=` ensures the transition fires even if the counter overshoots.

**Event emission before transition.** The `s1_progress` event is published before checking the threshold. This ensures every completion is visible to the SSE stream, even if it's the one that triggers the transition.

## The transition methods

```python
async def _transition_s2(self, run_id):
    await self._r.set(f"run:{run_id}:stage", "S2_REDUCE")
    await self._xadd_event(run_id, "stage_started", {"stage": "S2_REDUCE", "total_items": 1})

    from app.workers.tasks import s2_aggregate_task
    s2_aggregate_task.delay(run_id)
```

Each transition:
1. Updates the stage key
2. Publishes a `stage_started` event
3. Dispatches the next task(s)

**Lazy imports:** `from app.workers.tasks import s2_aggregate_task` is inside the method, not at the top of the file. This breaks the circular dependency between `orchestrator.py` (which dispatches tasks) and `tasks.py` (which imports the orchestrator for callbacks). Lazy imports resolve this by deferring the import until the method is actually called.

## S4 and checkpointing

S4 has extra logic:

```python
async def on_s4_complete(self, run_id, persona_id, top_5=None):
    done = await self._r.incr(f"run:{run_id}:s4:done")
    config = await self._load_config(run_id)

    await self._r.write_checkpoint(run_id, "s4", done)

    await self._xadd_event(run_id, "vote_cast", {
        "persona_id": persona_id,
        "top_5": top_5 or [],
        "completed": done,
        "total": config.num_personas,
    })

    if done >= config.num_personas:
        await self._transition_s5(run_id)
```

**`write_checkpoint`** stores `checkpoint:{run_id}:s4 = done` in Redis. This is the progress marker for crash recovery. If the system fails after 60 of 100 personas have voted, the `recover()` method reads the checkpoint and dispatches only the remaining 40.

The checkpoint is written on every single S4 completion — 100 extra Redis writes per run. Each write takes microseconds. The payoff: up to 99 saved LLM calls on crash recovery. This is a clear cost/benefit win.

## Error handling: `on_failure()`

```python
async def on_failure(self, run_id, stage, error, recoverable=False):
    await self._r.set(f"run:{run_id}:status", "failed")
    await self._r.set(f"run:{run_id}:stage", "FAILED")
    await self._xadd_event(run_id, "pipeline_error", {
        "stage": stage,
        "error": error,
        "recoverable": recoverable,
    })
    await self._set_run_ttl(run_id)
```

**Terminal state.** Once a run is marked "failed," no further transitions happen. Other in-flight tasks for the same run might still be executing (they were already dispatched), but their completions will increment counters that nobody is watching — the orchestrator has already moved to FAILED.

**The `recoverable` flag** tells the SSE consumer (the frontend) whether the user can trigger crash recovery. If `recoverable=True`, the frontend can show a "Retry from checkpoint" button.

**TTL setting:** `_set_run_ttl` sets a 24-hour expiry on all run keys. This prevents Redis from accumulating state from old runs. After 24 hours, the run data is automatically garbage-collected.

## Finalization

```python
async def _finalize(self, run_id, config):
    # Read all S6 results
    results = []
    raw_rankings = await self._r.get(f"top_scripts:{run_id}")
    rankings = S5Rankings.model_validate_json(raw_rankings)

    for ranked in rankings.top_10[:config.top_n]:
        raw = await self._r.get(f"s6_result:{run_id}:{ranked.script_id}")
        result = FinalResult.model_validate_json(raw)
        result.rank = ranked.rank
        result.vote_score = ranked.score
        results.append(result)

    output = S6Output(
        run_id=run_id,
        results=results,
        creator_profile=config.creator_profile,
        completed_at=datetime.now(UTC),
    )

    await self._r.set(f"results:final:{run_id}", output.model_dump_json(), ttl=TTL_SECONDS)
    await self._r.set(f"run:{run_id}:status", "completed")
    await self._r.set(f"run:{run_id}:stage", "DONE")
    await self._xadd_event(run_id, "pipeline_completed", {...})
    await self._set_run_ttl(run_id)
```

**Assembly from parts.** The orchestrator reads individual S6 results (one per top script), merges them with S5 ranking data, and constructs the final `S6Output`. This is the reduce step of the whole pipeline — assembling the final deliverable from distributed intermediate results.

**The `results:final:{run_id}` key** is what `GET /api/pipeline/results/{run_id}` reads. It's the single artifact that represents a completed pipeline run.

## The orchestrator as a design pattern

The orchestrator pattern has other names in the industry:

- **Saga pattern** in microservices: a coordinator that manages a multi-step distributed transaction
- **Process manager** in domain-driven design: a stateful object that routes events to handlers
- **Workflow engine** in enterprise systems: Temporal, Airflow, Step Functions

Flair2's orchestrator is a minimal version of these. It doesn't have durability (it runs in the worker process, not as a persistent service), doesn't have compensating transactions (no "undo S1 if S2 fails"), and doesn't have complex branching (no conditional paths based on intermediate results). But the core idea is the same: **a single component that knows the happy path, tracks progress through it, and handles deviations.**

If Flair2 grew more complex (conditional stages, A/B testing of prompts, human-in-the-loop approval), you'd eventually outgrow this hand-rolled orchestrator and reach for a tool like Temporal or Airflow. Knowing when to make that jump is a senior-level skill: too early and you're adding operational complexity for no benefit; too late and you're maintaining a bug-ridden custom workflow engine.

## What you should take from this

1. **Single writer eliminates coordination bugs.** If only one code path mutates state, you don't need locks, transactions, or conflict resolution.

2. **Atomic counters are distributed barriers.** `INCR` in Redis replaces `CountDownLatch` in Java or `WaitGroup` in Go. Same concept, distributed implementation.

3. **State machines make systems predictable.** A fixed set of states with deterministic transitions means you can reason about all possible behaviors. Debug by asking "what state are we in and what transition should fire next?"

4. **Lazy imports solve circular dependencies.** When A dispatches tasks defined in B, and B calls back into A, import B inside A's methods instead of at module level.

5. **The orchestrator pattern scales to arbitrary complexity** — but you should resist that complexity. Flair2's linear pipeline is simple enough for a hand-rolled orchestrator. Only reach for Temporal/Airflow when you have branching, loops, or human-in-the-loop steps.

---

***Next: [MapReduce: Fan-Out and Fan-In](11-mapreduce.md) — the counter pattern, distributed barriers, and what makes S1/S4 different from S2/S5.***
