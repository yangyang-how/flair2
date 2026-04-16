# 12. Checkpoint and Recovery

> A system that works until it crashes isn't reliable — it's lucky. This article covers how Flair2 saves progress during the most expensive pipeline stage and recovers from mid-execution failures.

## The economics of crash recovery

A full pipeline run makes roughly 261 LLM calls:
- S1: 100 calls (one per video)
- S3: 50 calls (one per script)
- S4: 100 calls (one per persona)
- S6: 10 calls (one per top script)
- S2, S5: 0 calls (pure Python)

Each LLM call costs time (~2-5 seconds for Kimi) and money (tokens aren't free). If the system crashes at S4 — after S1 (100 calls) and S3 (50 calls) are already done — restarting from scratch wastes 150 calls of already-completed work.

The question is: **how much work can you save on crash recovery, and what does the checkpoint mechanism cost?**

## Where checkpointing matters

Not every stage needs checkpointing. The decision framework:

| Stage | Tasks | Checkpoint? | Why |
|-------|-------|-------------|-----|
| S1 | 100 | No | First stage — nothing to lose by restarting |
| S2 | 1 | No | Single task, sub-second, no LLM call |
| S3 | 1 | No | Single task, sequential. Could be checkpointed but complexity isn't worth it |
| S4 | 100 | **Yes** | 100 LLM calls, most expensive stage, preceded by 150 calls of completed work |
| S5 | 1 | No | Single task, sub-second, no LLM call |
| S6 | 10 | No | Only 10 tasks, and S4 checkpoint covers the big risk |

**S4 is the sweet spot.** It's the most expensive fan-out stage AND it comes after significant prior work. A crash during S4 after 80 of 100 personas have voted would waste the most recovery time if there were no checkpoint.

## How checkpointing works

**File:** `pipeline/orchestrator.py` — `on_s4_complete`

```python
async def on_s4_complete(self, run_id, persona_id, top_5=None):
    done = await self._r.incr(f"run:{run_id}:s4:done")
    config = await self._load_config(run_id)

    # Checkpoint: persist progress
    await self._r.write_checkpoint(run_id, "s4", done)

    # ... publish SSE event ...

    if done >= config.num_personas:
        await self._transition_s5(run_id)
```

**File:** `infra/redis_client.py` — `write_checkpoint` and `read_checkpoint`

```python
async def write_checkpoint(self, run_id, stage, index):
    await self.set(f"checkpoint:{run_id}:{stage}", str(index))

async def read_checkpoint(self, run_id, stage):
    val = await self.get(f"checkpoint:{run_id}:{stage}")
    return int(val) if val is not None else None
```

Every time an S4 task completes, the orchestrator writes: `checkpoint:{run_id}:s4 = N` (where N is the number of completed personas). This is a single Redis `SET` — costs microseconds.

**The checkpoint is the high-water mark:** it records "at least N personas have completed." Because S4 tasks run concurrently and `INCR` is atomic, the checkpoint value increases monotonically.

## How recovery works

**File:** `pipeline/orchestrator.py` — `recover()`

```python
async def recover(self, run_id):
    config = await self._load_config(run_id)
    s4_done = await self._r.read_checkpoint(run_id, "s4") or 0

    await self._r.set(f"run:{run_id}:status", "running")
    await self._xadd_event(run_id, "pipeline_recovered", {
        "run_id": run_id,
        "s4_checkpoint": s4_done,
        "remaining_personas": config.num_personas - s4_done,
    })

    for i in range(s4_done, config.num_personas):
        s4_vote_task.delay(run_id, f"persona_{i}")
```

Recovery reads the checkpoint, calculates how many personas remain, and dispatches only the remaining tasks. If 80 of 100 personas completed before the crash, recovery dispatches 20 tasks — saving 80 LLM calls.

**What's preserved across a crash:**
- `run:{id}:config` — the full pipeline configuration (in Redis, TTL 24h)
- `s1_result:{id}:{vid}` — all S1 results
- `scripts:{id}` — all S3 scripts
- `s4_vote:{id}:persona_{N}` — each completed persona's vote
- `checkpoint:{id}:s4` — the high-water mark

**What might be lost:**
- `run:{id}:s4:done` — the counter. Recovery doesn't use the counter; it reads the checkpoint instead, which is more reliable because the counter can overshoot with duplicate deliveries.

## The M5-2 experiment: empirical evidence

The M5-2 experiment in `tests/experiments/test_failure_recovery.py` tested checkpoint recovery with controlled crash timing:

**Test design:** start a pipeline, forcibly kill the worker process after a specific number of S4 completions, then call `recover()` and measure how many LLM calls were saved.

**Results:**
- Crash at 30% (30/100 done): 30 calls saved, 70 redone
- Crash at 50% (50/100 done): 50 calls saved, 50 redone
- Crash at 73% (73/100 done): 73 calls saved, 27 redone

**Savings range: 30-73% depending on crash timing.** The later the crash, the more the checkpoint saves. The average saving across random crash points is ~50% — half the S4 work is preserved.

## What "exactly-once" really means

Checkpointing + recovery gives you "at-least-once" execution of S4 tasks. Some tasks near the checkpoint boundary might run twice:

```
Timeline:
  persona_79 completes → checkpoint = 79
  persona_80 starts executing on Worker A
  Worker A crashes
  checkpoint = 79 (persona_80 never incremented it)
  Recovery dispatches personas 79-99
  persona_79 runs again (duplicate)
  persona_80 runs again (was in-flight, now redone)
```

**Persona 79 runs twice** because the checkpoint was 79 when recovery fired. The second execution of persona_79 overwrites the Redis key `s4_vote:{id}:persona_79` with the same (or equivalent) result. No harm — the task is idempotent.

**True "exactly-once" would require:**
1. Writing the checkpoint and the result in a single atomic transaction
2. Using the checkpoint as an input filter on recovery ("skip persona_79 because its result exists")

Option 2 is what most production systems do. Flair2 takes the simpler path: accept the rare duplicate, rely on idempotency. For an LLM pipeline where two calls with the same prompt produce slightly different but equally valid output, this is acceptable.

## Checkpoint design trade-offs

### Granularity

Flair2 checkpoints after every S4 completion. Alternatives:

- **Every 10 completions:** 10x fewer Redis writes, but up to 10 tasks repeated on recovery
- **Every 1 completion:** maximum savings, but 100 Redis writes per run (current approach)
- **Never:** 0 Redis writes, but crash at S4 means restarting from S1

For Flair2, per-completion checkpointing is the right choice because: each LLM call costs 2-5 seconds, Redis writes cost microseconds, and 100 writes is negligible. The cost/benefit ratio is massively in favor of fine-grained checkpointing.

### Storage

Flair2 stores checkpoints in Redis (volatile memory with TTL). If Redis itself crashes, checkpoints are lost. In a production system, you'd write checkpoints to a durable store (DynamoDB, Postgres) that survives Redis restarts.

### Scope

Only S4 has checkpointing. A more robust system would checkpoint every fan-out stage. But the marginal benefit decreases: S1 has no prior work to protect (checkpointing S1 saves S1 progress but there's no expensive prior work), and S6 has only 10 tasks (not worth the complexity).

## Checkpoint patterns in the wild

| System | Checkpoint mechanism | Recovery strategy |
|--------|---------------------|-------------------|
| **Flair2** | Redis key per stage | Re-dispatch from checkpoint |
| **Spark** | RDD lineage + optional checkpoint to HDFS | Recompute lost partitions from lineage |
| **Kafka Streams** | Consumer offset committed to Kafka | Replay from last committed offset |
| **Flink** | Periodic snapshots to distributed storage | Restore from latest snapshot |
| **Database WAL** | Write-ahead log on disk | Replay log entries after crash |
| **Game saves** | Snapshot of game state to file | Load last save |

The pattern is always the same: **periodically record "how far we got," and on recovery, resume from that point.**

## What you should take from this

1. **Checkpoint the expensive parts.** Don't checkpoint everything — focus on stages where the cost of re-execution is high relative to the cost of the checkpoint write.

2. **Idempotency makes checkpointing simpler.** If tasks are idempotent, you don't need perfect checkpoint boundaries. A few duplicate executions near the boundary are harmless.

3. **The checkpoint is not the counter.** The `done` counter can overshoot (duplicate delivery) or be stale (process crash). The checkpoint is explicitly written as a reliable progress marker.

4. **Measure the savings empirically.** The M5-2 experiment proved that checkpointing saves 30-73% of S4 work depending on crash timing. Design speculation is useful; empirical evidence is conclusive.

5. **Recovery code is the most important code you'll write and the least often tested.** It runs in the rarest and most stressful conditions. Test it explicitly — the M5-2 experiment exists specifically to exercise the recovery path.

---

***Next: [The Six Stage Functions](13-the-six-stages.md) — pure functions, structured output, and the prompt-parse-validate pattern.***
