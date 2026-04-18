# 2. The Deployed Architecture

> Read the code, not the docs. Design documents describe the system at *t=0*. Code describes it at *t=now*. When they disagree, the code wins.

## A note on honesty

The original architecture doc (`design/architecture.md`) says the backend deploys to Railway and the frontend to Cloudflare Pages. In reality, the backend runs on AWS ECS Fargate with ElastiCache Redis, and the frontend is an S3 static website. The Gemini API is mentioned throughout the design docs and experiment reports — in reality, the production provider is Kimi (Moonshot AI), accessed over Kimi's coding endpoint using the Anthropic Messages API. The architecture doc hasn't been updated.

This is the single most common documentation failure in software: **design docs freeze at the point they were written.** Always verify against the code and the infrastructure. `git log`, `grep`, and `terraform plan` are more trustworthy than any markdown file.

This article describes the real system as of April 2026, verified against code and PR history.

## The topology

```
                          Internet
                             │
                         ┌───┴───┐
                         │  ALB  │  (Application Load Balancer)
                         └───┬───┘
                             │
                    ┌────────┼────────┐
                    │                 │
              ┌─────┴─────┐   ┌──────┴──────┐
              │  API Task  │   │  API Task   │  ECS Fargate (2-6 tasks)
              │  (FastAPI) │   │  (FastAPI)  │  auto-scales on CPU > 60%
              └─────┬──────┘   └─────┬───────┘
                    │                │
                    └────────┬───────┘
                             │
                    ┌────────┴────────┐
                    │   ElastiCache   │  Redis cache.t3.micro
                    │   (Redis 7)     │  db=0: state, db=1: Celery broker
                    └────────┬────────┘
                             │
                    ┌────────┼────────┐
              ┌─────┴──────┐  ┌──────┴──────┐
              │ Worker Task │  │ Worker Task │  ECS Fargate (2-4 tasks)
              │  (Celery)   │  │  (Celery)   │  auto-scales on CPU > 70%
              └─────┬───────┘  └─────┬───────┘
                    │                │
                    └────────┬───────┘
                             │
                    ┌────────┴────────┐
                    │    Kimi API     │  Anthropic Messages API
                    │ (Moonshot AI)   │  via anthropic Python SDK
                    └─────────────────┘


  Separately:     S3 bucket → static website hosting → Frontend (Astro + React)
```

## Component by component

### ALB (Application Load Balancer)

**What it is:** The entry point. An AWS-managed load balancer that receives HTTPS requests from the internet and distributes them across API tasks.

**Why it matters:** Without the ALB, you'd need to expose individual ECS tasks to the internet, manage their IP addresses, and handle health checking yourself. The ALB does three things: (1) distributes traffic across healthy tasks, (2) terminates SSL, (3) removes unhealthy tasks from the rotation automatically.

**Terraform module:** `terraform/modules/alb/main.tf`

**Key detail:** The ALB does health checks against `GET /api/health` on each API task. If a task stops responding, the ALB stops sending it traffic. This is why `backend/app/api/routes/health.py` exists — it's not for humans, it's for the load balancer.

### API Tasks (FastAPI on ECS Fargate)

**What they are:** Python processes running FastAPI. They handle HTTP requests — starting pipeline runs, streaming SSE events, returning results.

**File:** `backend/app/main.py` — the FastAPI app definition
**File:** `backend/app/api/routes/pipeline.py` — the pipeline endpoints
**File:** `backend/app/api/deps.py` — dependency injection (Redis pool, session ID)

**Scaling:** 2 to 6 tasks, auto-scaling when CPU exceeds 60%.

**What they do NOT do:** They never call the LLM. They never run pipeline stages. Their job is to accept requests fast, enqueue work, and stream progress. This separation is the most important architectural decision in the system.

**Why ECS Fargate:** Fargate is "serverless containers" — you give AWS a Docker image and a CPU/memory spec, and it runs it without you managing servers. Compared to EC2 (you manage the machine) or Lambda (limited to 15 minutes, cold starts), Fargate is the right fit for a long-running HTTP server that needs to hold SSE connections open.

### ElastiCache Redis

**What it is:** AWS-managed Redis. One `cache.t3.micro` instance running Redis 7.

**The five roles it plays** (each gets a deeper treatment in [Article 17](17-redis-nervous-system.md)):

1. **Celery message broker** (db=1) — the queue that workers pull tasks from
2. **Pipeline state store** (db=0) — `run:{id}:status`, `run:{id}:stage`, `run:{id}:config`
3. **SSE event stream** (db=0) — Redis Streams at `sse:{run_id}`, consumed by the SSE manager
4. **Rate limiter** (db=0) — `ratelimit:{provider}` counters with TTL-based windowing
5. **Idempotency cache** (db=0) — SETNX-based deduplication of LLM results

**Key design choice:** db=0 for application state, db=1 for the Celery broker. This prevents Celery's internal bookkeeping from colliding with application keys. See `backend/app/config.py` lines 11 and 44 — `redis_url` points to db=0, `celery_broker_url` points to db=1.

**The danger of one Redis:** Convenient but risky. If Redis goes down, everything stops — the queue, the state, the SSE stream, the rate limiter, the cache. You've created a single point of failure wearing five hats. For a prototype and a course project, this is fine. For production at scale, you'd split the broker onto a separate Redis instance at minimum.

### Worker Tasks (Celery on ECS Fargate)

**What they are:** Python processes running a Celery worker. They pull tasks from the Redis broker, call the LLM (Kimi), write results back to Redis, and notify the orchestrator.

**File:** `backend/app/workers/celery_app.py` — Celery configuration
**File:** `backend/app/workers/tasks.py` — the task definitions

**Scaling:** 2 to 4 tasks, auto-scaling when CPU exceeds 70%.

**The irony:** Workers are IO-bound, not CPU-bound. They spend almost all their time waiting for Kimi to respond. The M5-4 Locust experiment proved this: at K=500 concurrent users, Worker CPU peaked at 7.14%. Scaling on CPU > 70% means the workers will almost never scale up — the trigger is wrong. The correct signal would be Celery queue depth (`LLEN celery` in Redis). This is discussed in [Article 21](21-ecs-fargate.md).

### Kimi API (Moonshot AI)

**What it is:** The LLM provider. Every stage that needs AI reasoning (S1 analyze, S3 generate, S4 vote, S6 personalize) calls Kimi.

**File:** `backend/app/providers/kimi.py`
**File:** `backend/app/providers/registry.py`

**How it connects:** Kimi's coding endpoint speaks the **Anthropic Messages API** at `/coding/v1/messages`. The `KimiProvider` uses the `AsyncAnthropic` client with `base_url="https://api.kimi.com/coding"` and a `default_headers` override for User-Agent (Kimi's endpoint whitelists approved coding agents — Claude Code, Kimi CLI, etc.). An earlier version of the endpoint spoke OpenAI's `chat/completions` schema; that surface went dead in early 2026 and we migrated to Anthropic's SDK. See [Article 15](15-kimi-and-openai-compatibility.md) for the migration story.

**The migration stories:** Plural, now. First Gemini → Kimi (PR #95: "remove Gemini secret requirement"), driven by Gemini's intermittent 500s and rate-limit issues. Then OpenAI SDK → Anthropic SDK, driven by Kimi deprecating their OpenAI-compatible shim. Both migrations only touched `providers/kimi.py` because every stage calls through the `ReasoningProvider` Protocol. The `GeminiProvider` class still exists; it's just not wired up in production.

### Frontend (Astro + React on S3)

**What it is:** A static website built with Astro (generates static HTML) and React islands (interactive components hydrated client-side). Hosted on S3 with static website hosting enabled.

**File:** `frontend/astro.config.mjs` — `output: "static"` means the build produces plain HTML/CSS/JS files
**File:** `frontend/package.json` — Astro, React 19, Framer Motion for animations, Tailwind for styling

**Why "islands":** Astro's architecture means most of the page is static HTML. Only the interactive parts (pipeline visualizer, voting animation, results view) are React components that hydrate in the browser. This keeps the JavaScript bundle small — you only ship code for the parts that actually need interactivity.

**Why S3, not CloudFront:** Originally planned for CloudFront (CDN), but simplified to S3 static website hosting (PR #107). For a course project with limited traffic, the CDN layer adds complexity without meaningful benefit. The Astro config still has `@astrojs/cloudflare` as a dependency — legacy from the original plan, never removed.

### The dormant services

These are provisioned by Terraform but not used in the application's hot path:

- **DynamoDB** — `terraform/modules/dynamodb/main.tf` creates `pipeline_runs` and `video_performance` tables. `backend/app/infra/dynamo_client.py` has a complete client. But nothing in the API or worker code imports it. Results live in Redis with a 24-hour TTL. DynamoDB is the escape hatch for when Redis TTLs become a problem.

- **S3 (data bucket)** — `terraform/modules/s3/main.tf` creates a bucket for pipeline outputs. `backend/app/infra/s3_client.py` has upload/download/presigned-URL methods. Not imported by the hot path. Same story: future persistence layer.

- **Lambda** — `terraform/modules/lambda/` exists. Was planned for S7 video generation. Never built.

These dormant services illustrate **pragmatic scoping**: provision the infrastructure, write the client code, but don't wire it in until you need it. The cost of having the Terraform module and the client class is near zero. The cost of wiring them into the hot path before they're needed is debugging time and operational complexity.

## The three layers of distribution

This is the conceptual framework for understanding the whole system:

**Layer 1 — Edge to API.** The browser talks to the ALB over the internet. The ALB routes to an API task. This is standard web architecture. The distribution problem here is availability (what if an API task dies?) and load balancing (how do you spread traffic evenly?).

**Layer 2 — API to Workers.** The API task enqueues work on Redis. Workers pull work from Redis. This is the task queue pattern. The distribution problem here is decoupling (the API doesn't know or care which worker handles the task) and resilience (if a worker dies, the task can be retried by another worker).

**Layer 3 — Workers coordinating with each other.** Within one pipeline run, multiple workers process S1 tasks concurrently. They need to know when all S1 tasks are done so S2 can start. The distribution problem here is coordination without shared memory — they can't just check a variable, they have to use Redis counters and atomic increments.

Each layer has different failure modes, different scaling characteristics, and different tools. Most of what you'll learn in this series is about Layers 2 and 3 — that's where the interesting distributed systems thinking lives.

---

***Next: [How to Read This Codebase](03-how-to-read-this-codebase.md) — the directory map, module boundaries, and where to start.***
