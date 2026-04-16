# 7. What Celery Is (and Isn't)

> The task queue is the most important pattern in this architecture. Without it, the API would block on every LLM call, the system couldn't scale, and a single crash would destroy in-flight work. This article builds the mental model from scratch.

## Start with the problem

You have a web server that needs to do something slow. An LLM call takes 2-5 seconds. A pipeline run makes 261 of them. If the web server does the work itself:

- It holds an HTTP connection open for 15 seconds per request
- Its worker pool (the threads/processes handling HTTP requests) fills up with ~10 concurrent users
- If the server process crashes, all in-flight work is lost
- You can't scale the "accept requests" part independently of the "do LLM calls" part

The task queue pattern solves all four problems at once.

## The three components

Every task queue system has three parts. Understanding them is more important than understanding any specific tool (Celery, Sidekiq, Bull, etc.):

### 1. The Producer

The code that creates tasks. In Flair2, this is the orchestrator:

```python
s1_analyze_task.delay(run_id, video.model_dump_json())
```

`.delay()` serializes the function name and arguments into a message and pushes it onto the queue. The producer doesn't run the task — it just announces that work needs to be done.

### 2. The Broker

The message queue that sits between producers and consumers. In Flair2, this is Redis (database 1). The broker's job:

- Accept messages from producers
- Store them reliably until a consumer picks them up
- Deliver each message to exactly one consumer (not broadcast to all)
- Redeliver if a consumer fails to acknowledge

The broker is conceptually a FIFO queue: messages go in one end, come out the other. Common brokers: Redis, RabbitMQ, Amazon SQS, Apache Kafka.

### 3. The Consumer (Worker)

A process that pulls tasks from the broker and executes them. In Flair2, these are Celery worker processes running on separate ECS Fargate tasks:

```bash
celery -A app.workers.celery_app worker --loglevel=info
```

The worker runs in an infinite loop: pull a task from the queue, execute it, acknowledge completion, pull the next one. Multiple workers can run concurrently — the broker ensures each task is delivered to only one worker.

## The flow

```
Orchestrator  ───delay()──►  Redis (broker)  ◄───pull───  Worker 1
                                             ◄───pull───  Worker 2
                                             ◄───pull───  Worker 3
```

When the orchestrator calls `s1_analyze_task.delay(run_id, video_json)`:

1. Celery serializes the task name (`"app.workers.tasks.s1_analyze_task"`) and arguments (`[run_id, video_json]`) into a JSON message
2. The message is pushed onto a Redis list (the queue)
3. A worker that's idle runs `BLPOP` on that list — a blocking pop that waits until a message appears
4. The worker deserializes the message, imports the function, and calls it with the arguments
5. If the function completes successfully, the worker acknowledges the task (removes it from the "in progress" tracking)
6. If the function crashes, the task is redelivered to another worker (depending on configuration)

## What Celery adds on top

Celery is a Python library that implements this pattern with batteries included. It's not the only option (you could build the same thing with raw Redis + a loop), but it handles many edge cases:

- **Task routing:** different tasks can go to different queues, handled by different workers
- **Retry logic:** automatic retry with exponential backoff on failure
- **Rate limiting:** per-task concurrency limits
- **Monitoring:** visibility into what's running, what's pending, what failed
- **Result storage:** task return values saved to a result backend (Redis, in this case)
- **Serialization:** automatic JSON/pickle serialization of task arguments and results
- **Signals:** hooks for task lifecycle events (before start, after success, on failure)

Flair2 uses a subset of these features. The `celery_app.py` configuration is surprisingly short:

```python
celery_app = Celery("flair2")
celery_app.conf.update(
    broker_url=settings.celery_broker_url,     # Redis db=1
    result_backend=settings.redis_url,          # Redis db=0
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
```

Each of these settings has consequences. [Article 8](08-celery-configuration.md) covers them in depth.

## Why not just `asyncio.create_task()`?

FastAPI supports background tasks natively:

```python
# This is NOT what Flair2 does
@app.post("/start")
async def start(background_tasks: BackgroundTasks):
    background_tasks.add_task(run_pipeline, config)
    return {"status": "started"}
```

This creates an `asyncio` task in the same process. The work runs "in the background" of the same Python process that served the request. Here's why this doesn't work for Flair2:

**Problem 1: Process death kills the work.** If the API process crashes, restarts, or is replaced by a new deployment, all background tasks die with it. With Celery, the task is on the broker — if a worker dies, another worker picks it up.

**Problem 2: No scaling.** Background tasks run in the same process as HTTP handlers. You can't add more "background task capacity" without also adding more "HTTP request capacity." With Celery, workers scale independently.

**Problem 3: Resource competition.** Background tasks share the event loop with HTTP handlers. A CPU-intensive background task (or one that blocks the event loop) degrades HTTP response times. Workers are separate processes — their work doesn't affect the API.

**Problem 4: No visibility.** What's running? What's queued? What failed? With `asyncio.create_task()`, you'd have to build your own monitoring. Celery provides this out of the box.

**When `asyncio.create_task()` IS fine:** short tasks (under a few seconds), non-critical work (a failed email doesn't need retry), single-instance apps (no scaling needed). Sending a welcome email after signup? Fine. Running a 15-second AI pipeline? No.

**Rule of thumb:** if the work takes longer than your HTTP timeout, if a failure needs recovery, or if you need to scale work processing independently of request handling — use a task queue.

## The task definition pattern

**File:** `backend/app/workers/tasks.py`

Every Celery task in Flair2 follows the same pattern:

```python
@celery_app.task(name="s1_analyze")
def s1_analyze_task(run_id: str, video_json: str):
    async def _run():
        redis_client = RedisClient(settings.redis_url)
        try:
            config = await _load_config(redis_client, run_id)
            provider = _get_provider(config)
            video = VideoInput.model_validate_json(video_json)

            await _acquire_rate_limit_token(redis_client, provider.name)

            pattern = await provider.generate_text(...)
            await redis_client.set(f"s1_result:{run_id}:{video.video_id}", ...)

            orchestrator = Orchestrator(redis_client)
            await orchestrator.on_s1_complete(run_id, video.video_id)
        except (ProviderError, StageError) as e:
            orchestrator = Orchestrator(redis_client)
            await orchestrator.on_failure(run_id, "S1", str(e))
        finally:
            await redis_client.aclose()

    asyncio.run(_run())
```

**Notice:** the task function is sync (`def`, not `async def`), but it runs an async function inside using `asyncio.run()`. This is because Celery workers are synchronous by default — they run tasks in threads or processes, not an async event loop. The `asyncio.run()` creates a temporary event loop for each task execution.

**The five steps, always the same:**

1. **Load config** from Redis (the PipelineConfig is the source of truth)
2. **Get provider** (Kimi, Gemini, etc.) based on config
3. **Call the pure stage function** (no side effects, testable independently)
4. **Store the result** in Redis
5. **Notify the orchestrator** (which decides what happens next)

**Error handling:** each task catches `ProviderError` and `StageError` and reports failure to the orchestrator, which marks the run as failed and publishes a `pipeline_error` event to the SSE stream. The user sees the error in real time.

## Why JSON serialization?

```python
task_serializer="json",
accept_content=["json"],
```

Celery supports multiple serialization formats: JSON, pickle, YAML, msgpack. Flair2 uses JSON exclusively. Why?

**Pickle is dangerous.** Pickle can serialize arbitrary Python objects, including code. A malicious message on the broker could execute arbitrary code when deserialized by a worker. This is a known security issue. JSON is safe — it can only represent data (strings, numbers, booleans, arrays, objects).

**JSON is debuggable.** You can read a JSON message in Redis with `redis-cli` and understand what it says. Pickle is binary. When something goes wrong (and it will), being able to read the queued messages is invaluable.

**JSON is interoperable.** If you ever want a non-Python worker to process tasks, JSON works. Pickle is Python-only.

**The trade-off:** JSON can't serialize complex Python objects (datetime, custom classes). Task arguments must be primitive types or JSON-serializable strings. That's why tasks receive `video_json: str` (a JSON string) instead of `video: VideoInput` (a Pydantic object). The task deserializes it: `VideoInput.model_validate_json(video_json)`.

## Celery vs alternatives

Quick comparison of the options you'd consider:

| Tool | Language | Broker | Best for |
|------|----------|--------|----------|
| **Celery** | Python | Redis, RabbitMQ | Python backends with moderate scale |
| **RQ (Redis Queue)** | Python | Redis | Simple Python queues (less config than Celery) |
| **Dramatiq** | Python | Redis, RabbitMQ | Modern alternative to Celery (better defaults) |
| **Sidekiq** | Ruby | Redis | Ruby backends |
| **Bull/BullMQ** | Node.js | Redis | Node.js backends |
| **Amazon SQS** | Any | AWS-managed | Serverless, no broker to manage |
| **Apache Kafka** | Any | Kafka cluster | High-throughput event streaming |

Flair2 uses Celery because: Python backend (mandatory for the project), Redis already present (used for state + streaming), and Celery is the most documented Python task queue. A modern rewrite might choose Dramatiq (simpler, better defaults) or skip the framework entirely and use raw Redis queues (less magic, more control).

## What you should take from this

1. **The task queue pattern has three parts:** producer, broker, consumer. Learn the pattern, not the tool.

2. **The broker is the critical component.** If it goes down, no tasks can be enqueued or processed. It's a single point of failure unless you cluster it.

3. **Task queues solve four problems at once:** non-blocking requests, independent scaling, crash recovery, resource isolation. If you only need one of these, a simpler solution might work. If you need all four, a task queue is the standard answer.

4. **JSON serialization over pickle, always.** Safety, debuggability, and interoperability trump convenience.

5. **The task function is a thin wrapper.** The real logic lives in pure stage functions. The task handles infrastructure concerns (Redis, rate limiting, error reporting). This separation makes the stage functions testable without Celery running.

---

***Next: [Celery Configuration Deep Dive](08-celery-configuration.md) — what each config knob does, what breaks when you set it wrong.***
