# Flair2 Roadmap

> Single source of truth for what needs to be done, by whom, and in what order.
> Every row links to a GitHub issue. Update status here as issues close.

---

## Timeline

```
Mar 25          Mar 28          Apr 4           Apr 8           Apr 11          Apr 15
  |               |               |               |               |               |
  ├── M1: MVP ────┤               |               |               |               |
  |  (Sam)        |               |               |               |               |
  |               ├── M2: AWS ────┤               |               |               |
  |               |  (Jess)       |               |               |               |
  |               |               ├── M3: Dist ───┤               |               |
  |               |               |  (Both)       |               |               |
  |               |               |               ├── M4: Front ──┤               |
  |               |               |               |  (Sam)        |               |
  |               |               |               |               ├── M5: Exps ───┤
  |               |               |               |               |  (Both)       |
  ▼               ▼               ▼               ▼               ▼               ▼
  Start posting   MVP done        AWS deployed    Pipeline on     Frontend +      Experiments
  videos daily    locally         and reachable   AWS works       feedback live   + write-up
```

---

## Parallel Tracks

| Week | Sam | Jess | Sync Point |
|------|-----|------|------------|
| Mar 25-28 | **M1**: First real pipeline run + first posted video | **M2**: Terraform, VPC, S3, DynamoDB, Redis, ECS, ALB | None — fully independent |
| Mar 28-Apr 4 | **M4** (start): Astro scaffold, create page | **M2** (finish) + **M3** (start): Celery, orchestrator | — |
| Apr 4-8 | **M4**: Pipeline viz, voting animation, results page | **M3**: Rate limiter, SSE, checkpoints | **M3-1**: Sam's stage functions integrate into Jess's API |
| Apr 8-11 | **M4**: Performance tracking, insights dashboard | **M3-5**: Multi-user validation | **M3-4**: SSE streaming connects frontend ↔ backend |
| Apr 11-15 | Help with experiments, polish frontend | **M5**: Run experiments, collect data | Both run experiments together |

---

## M1: MVP Pipeline — Sam (by Mar 28)

Get a working pipeline running locally that generates scripts and video prompts. Start posting videos.

| Status | Issue | Title | Size | Depends on |
|--------|-------|-------|------|-----------|
| ✅ | [#16](../../issues/16) | Project scaffolding + Pydantic models | S | — |
| ✅ | [#17](../../issues/17) | Provider interface + Gemini implementation | S | #16 |
| ✅ | [#18](../../issues/18) | S1 analyze + S2 aggregate (MapReduce Cycle 1) | M | #17 |
| ✅ | [#19](../../issues/19) | S3 generate + S4 vote + S5 rank (MapReduce Cycle 2) | M | #18 |
| ✅ | [#20](../../issues/20) | S6 personalize + local runner + CLI | M | #19 |
| ⬜ | [#21](../../issues/21) | Download dataset + first real pipeline run | M | #20 |
| ⬜ | [#22](../../issues/22) | Generate + post first video | M | #21 |

> **#16–#20 are done** — implemented in PR #15. Merge it, then #21 is next.

---

## M2: AWS Infrastructure — Jess (by Apr 4)

Deploy all AWS services. The goal is: ALB URL returns 200 from /api/health.

| Status | Issue | Title | Size | Depends on |
|--------|-------|-------|------|-----------|
| ⬜ | [#23](../../issues/23) | Terraform project + VPC + IAM roles | M | — |
| ⬜ | [#24](../../issues/24) | S3 bucket + DynamoDB tables | S | #23 |
| ⬜ | [#25](../../issues/25) | ElastiCache Redis + ECR repository | S | #23 |
| ⬜ | [#26](../../issues/26) | ECS Fargate + ALB (API service) | L | #23, #25 |
| ⬜ | [#27](../../issues/27) | ECS Fargate (Celery worker service) | M | #25, #26 |
| ⬜ | [#28](../../issues/28) | Lambda function for S7 video generation | M | #23, #24 |

> **Start here: #23** — everything else depends on VPC + IAM.

```
#23 (VPC + IAM)
 ├── #24 (S3 + DynamoDB)
 │    └── #28 (Lambda)
 └── #25 (Redis + ECR)
      └── #26 (ECS + ALB)
           └── #27 (Workers)
```

---

## M3: Distributed Pipeline — Both (by Apr 8)

Wire up the API, Celery workers, orchestrator, and distributed systems features.

| Status | Issue | Title | Size | Owner | Depends on |
|--------|-------|-------|------|-------|-----------|
| ⬜ | [#29](../../issues/29) | FastAPI routes + infra clients | L | Both | #26, #20 |
| ⬜ | [#30](../../issues/30) | Celery tasks + orchestrator state machine | L | Jess | #29, #27 |
| ⬜ | [#31](../../issues/31) | Rate limiter + SETNX cache | M | Jess | #30 |
| ⬜ | [#32](../../issues/32) | SSE streaming + checkpoint recovery | M | Both | #30 |
| ⬜ | [#33](../../issues/33) | Multi-user validation (3 concurrent runs) | M | Both | #30, #31 |

> **#29 is the integration point** — Sam's stage functions meet Jess's infrastructure.

```
#29 (API + infra clients) ← needs #26 (ECS) + #20 (stages)
 └── #30 (Celery + orchestrator)
      ├── #31 (Rate limiter + cache)
      │    └── #33 (Multi-user validation)
      └── #32 (SSE + checkpoints)
```

---

## M4: Frontend + Feedback Loop — Sam (by Apr 11)

Astro frontend with React islands for real-time visualization and performance tracking.

| Status | Issue | Title | Size | Depends on |
|--------|-------|-------|------|-----------|
| ⬜ | [#34](../../issues/34) | Astro project scaffold + Cloudflare Pages deploy | S | — |
| ⬜ | [#35](../../issues/35) | Create page (input form + model selection) | M | #34, #29 |
| ⬜ | [#36](../../issues/36) | Pipeline visualizer (SSE React island) | L | #34, #32 |
| ⬜ | [#37](../../issues/37) | Voting animation (100-avatar React island) | L | #34, #32 |
| ⬜ | [#38](../../issues/38) | Results page + video player | M | #34, #29 |
| ⬜ | [#39](../../issues/39) | Performance tracking page + feedback API | M | #34, #29 |
| ⬜ | [#40](../../issues/40) | Insights dashboard + runs page | M | #39 |

> **#34 can start immediately** (no backend dependency). Sam can scaffold the frontend while Jess builds AWS.

---

## M5: Experiments + Write-up — Both (by Apr 15)

Run the three distributed systems experiments and collect data for the course write-up.

| Status | Issue | Title | Size | Owner | Depends on |
|--------|-------|-------|------|-------|-----------|
| ⬜ | [#41](../../issues/41) | Experiment 1: Multi-tenant backpressure | L | Both | #33, #31 |
| ⬜ | [#42](../../issues/42) | Experiment 2: Failure recovery + run isolation | L | Both | #32, #33 |
| ⬜ | [#43](../../issues/43) | Experiment 3: Cross-user cache concurrency | L | Both | #31, #33 |
| ⬜ | [#44](../../issues/44) | CI/CD pipeline (GitHub Actions) | S | Jess | — |

> **#44 can start anytime** — no dependencies. Good first-day task for Jess alongside Terraform.

---

## Critical Path

The longest dependency chain determines the project deadline:

```
#23 → #25 → #26 → #29 → #30 → #31 → #33 → #41/#42/#43
 VPC   Redis   ECS    API   Celery  Rate    Multi   Experiments
                                    limit   user
```

**If any of these slip, experiments get compressed.** Everything else has float.

---

## Quick Reference

**Total issues:** 29
**Sam's issues:** 14 (M1 + M4)
**Jess's issues:** 9 (M2 + M3 #30, #31 + M5 #44)
**Both:** 6 (M3 #29, #32, #33 + M5 #41, #42, #43)

**Size breakdown:** 6 Small (half day) · 15 Medium (1 day) · 8 Large (2-3 days)

**Where to start right now:**
- **Sam:** Merge PR #15, then #21 (download dataset, first real run)
- **Jess:** #23 (Terraform + VPC + IAM) and #44 (CI/CD — quick win)
