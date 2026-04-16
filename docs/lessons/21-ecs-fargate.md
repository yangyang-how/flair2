# 21. ECS Fargate: Two Services, One Cluster

> The decision to run API and Worker as separate ECS services with independent scaling policies is one of the most important infrastructure choices in Flair2. This article explains why, and reveals a scaling bug that the M5-4 experiment exposed.

## What ECS Fargate is

**ECS (Elastic Container Service)** runs Docker containers on AWS. **Fargate** is the serverless launch type — you specify a Docker image, CPU, and memory, and AWS handles the underlying servers. You never SSH into a machine, manage an OS, or patch a kernel.

**Compared to alternatives:**
- **EC2:** you manage the machine. More control, more operational burden.
- **Lambda:** per-request serverless. 15-minute timeout, cold starts. Wrong for long-running servers and persistent connections.
- **Fargate:** managed containers. Right for long-running HTTP servers (API) and worker processes (Celery). No server management, no cold starts.

## Two services, one cluster

Flair2 runs two ECS services on one cluster:

| Service | Container | Min/Max Tasks | Scaling metric | Scaling target |
|---------|-----------|---------------|----------------|----------------|
| **API** | FastAPI + Uvicorn | 2 / 6 | CPU utilization | 60% |
| **Worker** | Celery worker | 2 / 4 | CPU utilization | 70% |

**Why two services?** Because API and Worker have fundamentally different resource profiles:

**API tasks are request-bound.** They spend time accepting HTTP connections, parsing requests, making short Redis calls, and holding SSE connections. Their CPU usage scales with the number of concurrent HTTP requests.

**Worker tasks are IO-bound.** They spend time waiting for Kimi API responses (2-5 seconds per call). Their CPU usage stays near zero regardless of workload — they're waiting, not computing.

If you put both in one service, scaling on CPU would only respond to API load (the only thing using CPU). Worker capacity would be a side effect of API scaling decisions. Separating them lets each scale on the metric that actually matters for that workload.

## The scaling bug

The M5-4 experiment revealed a fundamental problem with the Worker scaling policy:

```
Worker auto-scaling: CPU utilization > 70% → add tasks
M5-4 result: Worker CPU peaked at 7.14% at K=500
```

**The Worker will never scale up.** Its CPU target is 70%, but its actual CPU usage is 7% under maximum load. The scaling metric is wrong.

**Why CPU is wrong for IO-bound workers:** a Celery worker processing an LLM task does this:

```
t=0ms:     Pull task from Redis (0.5ms, uses CPU)
t=0.5ms:   Deserialize, load config (2ms, uses CPU)
t=2.5ms:   Rate limiter check (1ms, uses CPU)
t=3.5ms:   Call Kimi API and wait...
t=3503ms:  Response arrives, parse JSON (5ms, uses CPU)
t=3508ms:  Write result to Redis (0.5ms, uses CPU)
t=3508.5ms: Task complete
```

CPU active time: ~9ms. Total task time: ~3,500ms. CPU duty cycle: **0.26%**. Scaling on CPU utilization for this workload is like scaling a restaurant based on how busy the kitchen timer is — the timer clicks for 5 seconds every 30 minutes.

## What the correct metric is

**Celery queue depth:** `LLEN celery` in Redis shows how many tasks are waiting to be processed. If the queue is growing, workers aren't keeping up — add more. If it's empty, workers are idle.

```
Queue depth = 0:        Workers are keeping up. Don't scale.
Queue depth = 50:       Workers are falling behind. Scale up.
Queue depth > 100:      Workers are significantly behind. Scale up aggressively.
```

**How to implement:** ECS Application Auto Scaling supports custom CloudWatch metrics. You'd publish `celery_queue_depth` to CloudWatch (via a small Lambda function or a sidecar container that runs `redis-cli LLEN celery` periodically), then configure scaling to respond to it.

```
# Pseudocode — not in Flair2, but should be:
custom_metric "celery_queue_depth":
  target: 10           # Scale up when queue exceeds 10 tasks per worker
  scale_up_cooldown: 60s
  scale_down_cooldown: 300s
```

## Task definitions

Each ECS service has a task definition that specifies:
- Docker image (from ECR)
- CPU and memory allocation
- Environment variables (Redis URL, API keys via Secrets Manager)
- Log configuration (CloudWatch Logs)
- Health check

The API task definition runs:
```
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

The Worker task definition runs:
```
celery -A app.workers.celery_app worker --loglevel=info
```

Same Docker image, different entrypoint command. This is a common pattern — one image, multiple roles. The `Dockerfile` builds the entire application; the ECS task definition chooses which process to run.

## Minimum tasks: why 2, not 1

Both services have `min_tasks = 2`. Why?

**Availability during deployments.** When ECS deploys a new version, it starts a new task before killing the old one (rolling deployment). With `min_tasks = 1`, during deployment there's briefly 1 old + 1 new task. With `min_tasks = 1` and a failed deployment, you could end up with 0 tasks. `min_tasks = 2` ensures at least 1 healthy task survives a botched deployment.

**Multi-AZ distribution.** ECS distributes tasks across availability zones. With 2 tasks, one runs in each AZ. If an AZ goes down, the other keeps running. With 1 task in 1 AZ, an AZ failure means total downtime.

**Load distribution.** The ALB distributes requests across API tasks. With 1 task, there's no distribution — all requests hit one container. With 2 tasks, the load is split. The 2nd task also provides baseline capacity for traffic spikes before auto-scaling kicks in (scaling takes 1-2 minutes).

## Auto-scaling mechanics

ECS Application Auto Scaling works like a thermostat:

1. CloudWatch collects CPU metrics from ECS tasks (every 60 seconds)
2. Auto Scaling compares the metric to the target (60% for API, 70% for Worker)
3. If the metric exceeds the target, Auto Scaling adds tasks (up to `max_tasks`)
4. If the metric is below the target, Auto Scaling removes tasks (down to `min_tasks`)
5. Cooldown periods prevent thrashing (too-frequent scaling changes)

**M5-4 observation:** at K=500, the API auto-scaled from 2 to 3 tasks within ~2 minutes. CPU exceeded 60%, a new task was launched, and the load was redistributed. The system stabilized — but p95 was still 12 seconds because the bottleneck was the connection pool, not CPU capacity.

**Lesson:** auto-scaling responded correctly to its configured metric. The problem was that the metric (CPU) didn't capture the actual bottleneck (connection pool). Auto-scaling is only as good as the metric it watches.

## ECS Exec: live debugging

PRs #129 and #130 enabled ECS Exec — the ability to open a shell session inside a running ECS task:

```bash
aws ecs execute-command \
    --cluster flair2-dev \
    --task <task-id> \
    --container api \
    --interactive \
    --command "/bin/sh"
```

This was used during the M5-4 experiment to measure queue depth:
```bash
redis-cli -h <redis-host> LLEN celery
```

The result (0-1 tasks in queue) confirmed that Workers were keeping up and the bottleneck was elsewhere. Without ECS Exec, this measurement would have required deploying a custom monitoring tool.

**PR #130 note:** the task role was missing `ssmmessages` permissions — a one-line IAM fix that took its own PR. This is a typical infrastructure papercut: ECS Exec requires specific IAM permissions that aren't included in default roles.

## The Docker image

One Dockerfile builds the image. Key decisions:

**Multi-stage build:** the build stage installs dependencies, the runtime stage copies only what's needed. This keeps the final image small.

**`data/` in the image:** the video dataset is baked into the Docker image. This was the source of PRs #102, #109, #125, #126 — the `.dockerignore` excluded `data/`, so the pipeline couldn't find `sample_videos.json` at runtime. The fix was to ensure `data/` was included in the image (and also to include `pyproject.toml` for pytest config — PR #120).

**Same image, different command:** both API and Worker services use the same image. The ECS task definition specifies the container command (`uvicorn` vs `celery`). This simplifies CI/CD — one build produces one image that serves both roles.

## What you should take from this

1. **Separate services for separate scaling profiles.** If two components have different resource characteristics (CPU-bound vs IO-bound), run them as separate services with independent scaling policies.

2. **CPU is the wrong metric for IO-bound workers.** Queue depth, concurrent connections, or custom application metrics are better signals. CPU scaling only works for CPU-bound workloads.

3. **Minimum 2 tasks for availability.** One task in each AZ survives single-AZ failures, deployment rollbacks, and provides baseline capacity.

4. **Auto-scaling is only as good as its metric.** The system will scale perfectly against the metric you configure — even if that metric doesn't represent the real bottleneck.

5. **Same image, different command is a good pattern.** One build, one image, one push. Different ECS task definitions choose different entrypoints. Simpler CI/CD, consistent dependencies.

---

***Next: [CI/CD: The GitHub Actions Pipeline](22-cicd-github-actions.md) — the build-test-deploy flow and what it catches.***
