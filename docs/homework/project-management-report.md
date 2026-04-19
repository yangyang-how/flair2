# Flair2 — Project Management Report

**Team:** Sam Wu (@0b00101111) · Jess Zhang (@tyrahappy)
**Duration:** 2026-03-22 → 2026-04-18 (~4 weeks)
**Scope:** 262 commits · 112 merged PRs · 2 deployed services on AWS

---

## From Design to Final State

We started from a V1 hackathon prototype (`gemini-social-asset`) and rewrote it with engineering rigor: spec-first, TDD, CI/CD, two-service AWS architecture. Initial design decomposed the problem into six pipeline stages (S1–S6) and five milestones (M1–M5) planned on a parallel-track timeline.

```
 V1 prototype               V2 engineered system              Deployed
 ───────────────────────────────────────────────────────────────────────
 Monolithic main.py   →   modular (api/pipeline/workers)   →   ECS Fargate
 In-memory state      →   Redis + Celery coordination       →   ElastiCache
 Sequential pipeline  →   MapReduce fan-out/fan-in          →   20 concurrent
 Gemini only          →   pluggable provider registry       →   Kimi live
 No tests / CI        →   111 unit + 5 integration + M5/M6  →   GitHub Actions
```

## Work Breakdown (Parallel Tracks)

| Week | Sam (frontend + pipeline stages) | Jess (infra + distributed systems) | Sync point |
|------|----------------------------------|-------------------------------------|------------|
| Mar 22–28 | **M1** — stage functions S1–S6, first real pipeline run | **M2** — Terraform: VPC, ECS, ElastiCache, DynamoDB, S3 | Interface contract (issue #71) |
| Mar 28–Apr 4 | **M4** scaffold — Astro, create page | **M2** finish + **M3** — Celery, orchestrator, rate limiter | Contract #71 §3 — API routes |
| Apr 4–8 | **M4** — SSE pipeline visualizer, voting animation | **M3** — SSE manager, checkpoints, multi-user validation | Contract #71 §2 — SSE events |
| Apr 8–11 | **M4** — results page, polish | **M3-5** — integration tests, deploy workflow | First full E2E on AWS |
| Apr 11–15 | Experiments helper, design-language port | **M5** — M5-1/2/3 backpressure, recovery, cache experiments | Both: M5-4 Locust, M6 ElastiCache |
| Apr 15–18 | S1 grid viz, S4 vote matrix, observability | Deploy hardening, Terraform state import, destroy workflow | Final polish |

**PR split:** Sam 69 (62%), Jess 43 (38%). Every PR reviewed by the other.

## Problems Encountered & How We Broke Them Down

| # | Problem | How we found it | Resolution |
|---|---------|-----------------|------------|
| 1 | **Gemini intermittent 500s + rate limits** | First production run failed at S3 | Built provider registry → switched to Kimi in one PR (#95) |
| 2 | **Docker image missing dataset** — S1 500'd on every start | Frontend showed "Pipeline failed" with no worker activity | 4 PRs to root-cause: `.dockerignore` excluded `data/` (#102, #109, #125, #126) |
| 3 | **Kimi OpenAI-compatible shim deprecated** — all requests returned a misleading "temperature" error | Tests passed locally, production 400s | Migrated `KimiProvider` from OpenAI SDK → Anthropic Messages API |
| 4 | **Celery workers never registered tasks** — pipeline silently hung at `stage_started` | 2 events in SSE then nothing; only traceable via CloudWatch | One-line fix: `import app.workers.tasks` in `celery_app.py` (#140) |
| 5 | **Frontend faked progress when backend was stuck** | Stages showed "running" with no real work | Added single-writer event discipline, 30s stall detector with API probe (#136, #138) |
| 6 | **Terraform state drift after CI change** | "ELB already exists" on every `terraform apply` | Wrote idempotent import workflow + script (#162) — discovers each resource by tag/name and imports ~50 resources |
| 7 | **Kimi concurrency 429s killed S4** at ~40 personas | Pipeline visibly failed with "rate limited" even though daily quota was at 1% | Two-layer fix: RedisSemaphore (cap at 29 in-flight) + retry-budget-per-error-class with 8/20/45/90s backoff + jitter (#164) |
| 8 | **One bad video killed whole S1 run** | Sparse TikTok transcripts hit schema validation | Skip-and-continue (#156): mark video skipped, let S2 aggregate the rest |
| 9 | **Stragglers (99/100) hung pipeline** because of long retry budget | UI showed "Pipeline appears stalled" at 99/100 | 95% completion threshold with SETNX-guarded transition (#165) |
| 10 | **S3 client-side routes 404'd** after deploy — "Start Pipeline" bounced to home page | User-reported | S3 error doc only serves ROOT index.html; switched path-based routes to query params (#134) |

## Process Discipline That Held

- **Interface contract (issue #71) upfront** — documented every Redis key, every SSE event, every API endpoint. Let Sam and Jess work independently for weeks and integrate cleanly.
- **One PR, one fix** — 112 PRs averaged 4 files each. Every PR title used conventional prefixes (`feat:`, `fix:`, `chore:`, `docs:`) for grep-friendly history.
- **Hard branch protection on `main`** — Sam and Jess set a GitHub ruleset that *physically blocks* direct pushes and requires ≥1 approving review from the other team member before merge (admin override disabled). This turned "we should review each other's work" from a norm into an enforced gate. Effect: every one of the 112 merged PRs has at least one reviewer's signature; neither of us can ship without the other reading the diff. On multiple occasions Jess's review caught issues Sam missed (and vice-versa) before they hit production.
- **Tests before features** — 105 unit tests existed before the first real pipeline run. Grew to 111 by the end. Caught the `RateLimitError` retry countdown bug pre-deploy.
- **Test the failure paths explicitly** — M5-2 (failure recovery) validated the checkpoint-and-resume code before we ever needed it. Saved ~50% of LLM calls on the first real crash.

## What the Final State Runs

**AWS** `314727362981` / `us-west-2`: VPC, 2 public + 2 private subnets, ECS Fargate cluster (API + Worker services, 2–6 / 2–4 tasks with autoscaling), ElastiCache Redis, ALB, S3 static site, DynamoDB, ECR, IAM roles — all Terraform-managed.
**CI/CD:** GitHub Actions runs lint+test on every push; merges to main auto-deploy Docker image → ECR → ECS and static site → S3.
**Pipeline:** 100 real viral TikTok videos analyzed in ~15s (20 concurrent workers, bounded by Kimi's concurrency semaphore), 20 scripts generated on-niche, 42 predefined personas vote, top 10 personalized per creator profile.
