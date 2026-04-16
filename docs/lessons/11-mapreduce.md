# 11. MapReduce: Fan-Out and Fan-In

> MapReduce is one of the most important ideas in distributed computing. Flair2 uses it twice in every pipeline run. This article explains the pattern, how Flair2 implements it, and where you'll see it again.

## The idea in 30 seconds

You have a large problem. You split it into N independent pieces (map), solve each piece concurrently, then combine the N results into one answer (reduce).

```
Input ──► Split ──► Map₁ ──►─┐
                    Map₂ ──►─┤
                    Map₃ ──►─┤──► Reduce ──► Output
                    ...  ──►─┤
                    Mapₙ ──►─┘
```

**Map** = transform each piece independently. No piece needs to know about any other piece.
**Reduce** = combine all pieces into a single result. Requires all map outputs as input.

The power is in the word "independently." Because map tasks don't depend on each other, they can run concurrently — on 2 machines or 2,000. The speedup is limited only by how many workers you have.

## Flair2's two MapReduce cycles

### Cycle 1: Discover patterns

```
100 videos ──► S1 Map (100 tasks) ──► 100 S1Patterns
                                           │
                                     S2 Reduce (1 task)
                                           │
                                     1 S2PatternLibrary
```

**Map (S1):** each task analyzes one video and extracts structural patterns (hook type, pacing, emotional arc, retention mechanics). Each task is independent — analyzing video #42 doesn't require knowing anything about video #17.

**Reduce (S2):** reads all 100 S1 results, groups them by pattern type, counts frequencies, sorts by popularity. Produces one unified pattern library.

### Cycle 2: Evaluate scripts

```
100 personas ──► S4 Map (100 tasks) ──► 100 PersonaVotes
                                             │
                                       S5 Reduce (1 task)
                                             │
                                       Top 10 S5Rankings
```

**Map (S4):** each persona reads all 50 candidate scripts and picks their top 5. Each persona votes independently — persona #42 doesn't know what persona #17 voted for.

**Reduce (S5):** reads all 100 votes, applies weighted scoring (1st pick = 5 points, 5th pick = 1 point), ranks all scripts by total score, returns the top N.

## How fan-out works in code

**The dispatch** (in `orchestrator.py`):

```python
for video in videos:
    s1_analyze_task.delay(run_id, video.model_dump_json())
```

This loop pushes 100 messages onto the Celery queue in rapid succession. Each message contains the `run_id` and one video's data (serialized as JSON). Workers pull these messages and execute them concurrently — limited only by the number of available worker slots and the rate limiter.

**The task** (in `tasks.py`):

```python
@celery_app.task(name="s1_analyze")
def s1_analyze_task(run_id: str, video_json: str):
    async def _run():
        # ... load config, get provider, rate limit ...
        video = VideoInput.model_validate_json(video_json)
        pattern = await s1_analyze(video, provider)
        await redis_client.set(
            f"s1_result:{run_id}:{video.video_id}",
            pattern.model_dump_json()
        )
        orchestrator = Orchestrator(redis_client)
        await orchestrator.on_s1_complete(run_id, video.video_id)
    asyncio.run(_run())
```

Each task: deserialize input → call pure function → store result in Redis → notify orchestrator. The result is stored at a key that includes the video ID, so 100 concurrent tasks write to 100 different keys. No conflicts.

## How fan-in works: the counter pattern

The hardest part of MapReduce in a distributed system is knowing when all map tasks are done. In a single process, you'd use a `CountDownLatch` or `WaitGroup`. In a distributed system, you have no shared memory.

Flair2's solution: an atomic counter in Redis.

```python
async def on_s1_complete(self, run_id, video_id):
    done = await self._r.incr(f"run:{run_id}:s1:done")  # atomic
    config = await self._load_config(run_id)

    if done >= config.num_videos:
        await self._transition_s2(run_id)
```

**How this works:**

1. Each worker, upon completing an S1 task, calls `INCR run:{id}:s1:done`
2. Redis `INCR` is atomic — even with 100 concurrent calls, each caller gets a unique sequence number (1, 2, 3, ..., 100)
3. Exactly one caller gets `done == 100` and triggers the transition
4. The other 99 callers get `done < 100` and do nothing

This is a **distributed barrier** — a synchronization point where N concurrent processes must all arrive before the next phase begins. The counter is the barrier implementation.

**Why `>=` instead of `==`:** as discussed in [Article 9](09-worker-lifecycle-and-failure.md), task redelivery (from `acks_late=True`) can cause the counter to exceed `num_videos`. Using `>=` ensures the transition fires even if the counter overshoots.

## The reduce phase

**S2 Aggregate** (`pipeline/stages/s2_aggregate.py`):

```python
def s2_aggregate(patterns: list[S1Pattern]) -> S2PatternLibrary:
    groups: dict[str, list[S1Pattern]] = defaultdict(list)
    for p in patterns:
        key = f"{p.hook_type} + {p.pacing}"
        groups[key].append(p)

    entries = []
    for key, group in groups.items():
        entries.append(PatternEntry(
            pattern_type=key,
            frequency=len(group),
            examples=[p.video_id for p in group[:5]],
            avg_engagement=0.0,
        ))

    entries.sort(key=lambda e: e.frequency, reverse=True)
    return S2PatternLibrary(patterns=entries, total_videos_analyzed=len(patterns))
```

Notice: **no LLM call.** S2 is pure Python. It groups patterns by type (`hook_type + pacing`), counts how often each type appears, and sorts by frequency. This is the classic reduce operation: take N items, produce one summary.

**S5 Rank** (`pipeline/stages/s5_rank.py`):

```python
def s5_rank(votes: list[PersonaVote], top_n: int = DEFAULT_TOP_N) -> S5Rankings:
    score_weights = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1}
    scores: Counter[str] = Counter()
    vote_counts: Counter[str] = Counter()

    for vote in votes:
        for position, script_id in enumerate(vote.top_5_script_ids):
            scores[script_id] += score_weights.get(position, 1)
            vote_counts[script_id] += 1

    top_scripts = scores.most_common(top_n)
    # ... build ranked list ...
```

Also pure Python. No LLM. Weighted vote aggregation using Python's `Counter` (which is essentially a hashmap with addition). This is a Borda count — a voting system where rank positions get different point values.

**Design insight:** reduce stages are algorithmic, not AI. The AI does the creative work (analyzing, generating, voting). The reduce stages do the mathematical work (aggregating, ranking). This separation is deliberate — you want the deterministic parts of your pipeline to be deterministic. Asking an LLM to aggregate or rank introduces nondeterminism where you don't need it.

## The connectors: S3 and S6

S3 and S6 don't fit neatly into the map/reduce model:

**S3 (Generate Scripts)** is between the two cycles. It reads the S2 pattern library and generates 50 candidate scripts. It's marked "SEQUENTIAL" because each script generation is a separate LLM call, but they run one at a time within a single task.

Why sequential? Because script diversity matters. If you fan out 50 parallel "generate a script" tasks, they might all produce similar scripts (each LLM call has no context about what the others generated). Sequential generation allows (in principle) each script to be informed by what was already generated.

**S6 (Personalize)** is a mini fan-out after the second reduce. It takes the top N scripts and personalizes each one independently. This is a map with N=10 — small enough that the overhead of fan-out is worth it.

## MapReduce at scale vs Flair2's scale

Classic MapReduce (Hadoop, Spark) operates on datasets with millions or billions of records, distributed across hundreds of machines. Flair2's MapReduce is tiny by comparison: 100 map tasks, 1 reduce task, 2-4 workers.

But the **patterns are identical:**

| Concept | Hadoop/Spark | Flair2 |
|---------|-------------|--------|
| Map dispatch | Job tracker assigns splits to nodes | Orchestrator dispatches Celery tasks |
| Map execution | Mapper processes one split | Worker runs one S1/S4 task |
| Intermediate storage | HDFS / shuffle files | Redis keys (`s1_result:{id}:{vid}`) |
| Barrier | All mappers report completion | `INCR` counter reaches threshold |
| Reduce | Reducer reads shuffled partitions | S2/S5 reads all results from Redis |
| Output | Written to HDFS | Written to Redis (`results:final:{id}`) |

The scale is different; the architecture is the same. If you understand Flair2's MapReduce, you understand Hadoop's — just add more machines and a distributed filesystem.

## Where MapReduce appears in the wild

- **Search engines:** map = index each web page independently; reduce = merge indexes
- **Log analysis:** map = parse each log file; reduce = aggregate error counts
- **Machine learning training:** map = compute gradient on each data batch; reduce = average gradients
- **Video transcoding:** map = transcode each segment; reduce = concatenate segments
- **This pipeline:** map = analyze each video / collect each vote; reduce = aggregate patterns / rank scripts

The pattern is everywhere because the problem is everywhere: "I have N independent pieces of work and need to combine the results."

## What you should take from this

1. **MapReduce is two ideas.** Fan-out (map) and fan-in (reduce). Both are useful independently, but they're most powerful together.

2. **Atomic counters are distributed barriers.** Redis `INCR` replaces in-memory synchronization primitives. The cost is a network round-trip per completion; the benefit is coordination across machines.

3. **Reduce stages should be deterministic.** Don't use an LLM where Python `Counter` will do. Reserve AI for creative work; use code for math.

4. **Fan-out granularity is a design decision.** Flair2 fans out one task per video (S1) and one task per persona (S4). You could fan out one task per batch of 10 videos — fewer tasks, less overhead, but coarser progress reporting and less parallelism.

5. **MapReduce is not just for big data.** Even at N=100, the pattern gives you parallelism, fault isolation (one failed S1 task doesn't affect others), and progress tracking. Scale is not the only reason to use it.

---

***Next: [Checkpoint and Recovery](12-checkpoint-and-recovery.md) — how the system saves progress and recovers from crashes mid-pipeline.***
