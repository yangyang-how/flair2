# Flair2 — AI Script Studio

> A distributed AI pipeline that turns viral video patterns into personalized TikTok scripts.

**Team:** Sam Wu · Jess Zhang  
**Course:** CS6650 Distributed Systems, Northeastern University, Spring 2026  
**Stack:** Python · FastAPI · Celery · Redis · AWS ECS Fargate · ElastiCache · Astro · React

---

## What We Built

Flair2 is a six-stage distributed AI pipeline for content creators. Given a creator profile, it:

1. **S1 (Map)** — Analyzes 100 viral videos concurrently to extract structural patterns
2. **S2 (Reduce)** — Aggregates patterns into a ranked pattern library
3. **S3** — Generates 20 candidate scripts concurrently using LLM
4. **S4 (Map)** — Runs 42 simulated personas voting on each script in parallel
5. **S5 (Reduce)** — Ranks scripts by Borda score
6. **S6** — Personalizes top 10 scripts to the creator's voice + generates video prompts

The frontend streams real-time progress via SSE as the pipeline runs, showing each stage completing live.

---

## Why We Built It

We wanted a project that was genuinely useful (a tool we'd actually use) but also a real distributed systems problem — not just a web app with a database. Every design decision in Flair2 maps directly to a course concept:

- **Fan-out / fan-in** — S1 and S4 dispatch N independent LLM tasks in parallel
- **Task queue** — Celery + Redis decouples the API layer from long-running LLM work
- **Shared state** — ElastiCache Redis coordinates N workers: state, SSE streaming, semaphore, cache
- **Backpressure** — TokenBucket rate limiter prevents provider 429s under concurrent load
- **Fault tolerance** — Checkpointed S4 so a crashed worker resumes from where it left off, not from scratch
- **Straggler mitigation** — 95% completion threshold so one slow LLM call doesn't block 41 completed ones

---

## Architecture

```
Browser (Astro + React)          Cloudflare Pages
    │  SSE  │  REST
    ▼       ▼
ALB ──── ECS API (FastAPI, 2+ tasks)
              │  Celery tasks
              ▼
         Redis db=1 (Celery broker)
              │
         ECS Workers (Celery, 2–10 tasks)
              │
         ├── Kimi / Gemini API   (LLM calls)
         ├── Redis db=0           (state, SSE streams, semaphore, SETNX cache)
         ├── DynamoDB             (run metadata, performance tracking)
         └── S3                  (pipeline results, dataset)
```

---

## How the Project Progressed

We ran on parallel tracks across 6 milestones over 6 weeks.

### Milestone 1 — MVP Pipeline (Sam, March 25–28)
First working local pipeline: provider interface, S1–S6 stage functions, Pydantic models. Goal was to get one full run working end-to-end before touching infrastructure.

### Milestone 2 — AWS Infrastructure (Jess, March 25–April 4)
Terraform from scratch: VPC, subnets, security groups, ECS Fargate, ALB, ElastiCache Redis, DynamoDB, S3, ECR, IAM roles. First deployment of the API container to ECS.

### Milestone 3 — Distributed Backend (Both, April 4–8)
Interface contract ([#71](https://github.com/yangyang-how/flair2/issues/71)) defined Redis key names and SSE events. Sam built API routes and SSE manager. Jess built Redis client abstraction, Celery workers, orchestrator, and rate limiter. Sync point: pipeline running on AWS end-to-end.

### Milestone 4 — Frontend (Sam, April 8–11)
Astro scaffold, pipeline visualizer with real-time stage animations, voting matrix showing 42 personas, results page with ranked scripts and video prompts.

### Milestone 5 — Experiments (Both, April 11–15)
Seven distributed systems experiments across three groups:
- **M5** (fakeredis): Backpressure, failure recovery, SETNX cache concurrency
- **M5-4** (AWS, Locust): API concurrent load test — found Redis connection pool exhaustion as the true bottleneck at K=500
- **M6** (AWS ElastiCache): Validated same properties on real Redis — SETNX atomicity holds to K=1,000, fails at K=5,000 due to client-side pool exhaustion

### Post-M5 — Refinements (April 15–20)
Fixed the most impactful bugs discovered during experiments: Celery task registration ([#140](https://github.com/yangyang-how/flair2/pull/140)), S3 sequential→concurrent generation ([#142](https://github.com/yangyang-how/flair2/pull/142)), 95% completion threshold for straggler mitigation ([#165](https://github.com/yangyang-how/flair2/pull/165)), predefined personas for consistent S4 voting ([#141](https://github.com/yangyang-how/flair2/pull/141)).

---

## Key Stats

| Metric | Value |
|--------|-------|
| Commits | 270+ |
| Pull Requests merged | 180+ |
| Issues tracked | 97 |
| Experiment tests | 61 automated + 3 live Locust runs |
| LLM calls per pipeline run | ~162 (42 persona votes + 100 video analyses + 20 scripts + 10 personalizations) |
| Pipeline completion time | 5–15 min (Kimi API, real run) |

---

## Running Locally

```bash
# Backend
cd backend
uv sync --extra dev        # install dependencies
cp .env.example .env       # add FLAIR2_KIMI_API_KEY
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Worker (separate terminal)
uv run celery -A app.workers.celery_app worker --loglevel=info

# Frontend
cd frontend
npm install
npm run dev
```

**Requires:** Redis running locally (`redis-server`), Python 3.11+, Node 22+.

---

## Running Tests

```bash
cd backend
uv run pytest tests/unit          # unit tests (fakeredis, no AWS)
uv run pytest tests/integration   # integration tests (fakeredis)
uv run pytest tests/experiments   # distributed systems experiments (fakeredis)
```

M5-4 load test (requires deployed AWS):
```bash
export ALB_URL=http://<your-alb-dns>
bash tests/experiments/run_load_test.sh
```

---

## Deploying to AWS

All infrastructure is managed with Terraform:

```bash
cd terraform
terraform init
terraform apply -var-file=environments/dev.tfvars
```

CI/CD is configured with GitHub Actions — push to `main` with changes in `backend/**` or `frontend/**` triggers an automatic Docker build, ECR push, and ECS force-deploy.

See [#97](https://github.com/yangyang-how/flair2/issues/97) for the full AWS deployment checklist.

---

## Experiments

Seven experiments validating the core distributed systems decisions:

| Report | What it covers |
|--------|---------------|
| [experiment-overview.md](experiment-overview.md) | All seven experiments — start here |
| [experiment-distributed-patterns.md](experiment-distributed-patterns.md) | Fan-out parallelism (26× speedup), straggler mitigation (89.6% time saved), exactly-once delivery |
| [experiment-m5-resilience.md](experiment-m5-resilience.md) | Backpressure, crash recovery, SETNX cache concurrency |
| [experiment-m5-load-test.md](experiment-m5-load-test.md) | Locust load test on AWS — K≤100 stable, K=500 Redis connection pool bottleneck |
| [experiment-m6-elasticache.md](experiment-m6-elasticache.md) | Real ElastiCache validation — SETNX atomicity, latency, memory |
| [experiments-report.pdf](experiments-report.pdf) | Formatted 5-page PDF with charts |

---

## Project Structure

```
backend/
  app/
    api/          FastAPI routes (pipeline, video, performance, health)
    pipeline/     Stage logic (s1–s6), orchestrator, prompts
    workers/      Celery app + task definitions
    infra/        Redis client, rate limiter, S3/DynamoDB clients
    providers/    Gemini + Kimi provider implementations
    models/       Pydantic schemas (stages, pipeline, errors)
  tests/
    unit/         Unit tests (fakeredis)
    integration/  Multi-user integration tests
    experiments/  M5/M6/distributed-patterns experiments
frontend/
  src/
    components/   PipelineVisualizer, VotingAnimation, ResultsView
    lib/          api-client.ts, sse-client.ts
    pages/        Astro pages
terraform/
  modules/        ECS, ALB, ElastiCache, DynamoDB, S3, ECR, IAM, Lambda
  environments/   dev.tfvars, prod.tfvars
```
