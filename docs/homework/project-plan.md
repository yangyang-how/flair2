# AI Campaign Studio (Flair2) — Project Plan

> Multi-stage AI pipeline that generates social media marketing campaigns.
> Two-person team: Sam (pipeline + frontend) and Jess (infrastructure + distributed systems).

---

## Timeline

```
 Mar 25       Mar 28       Apr 4        Apr 8        Apr 11       Apr 15
   |            |            |            |            |            |
   |--- M1 -----|            |            |            |            |
   | MVP Pipeline (Sam)      |            |            |            |
   |            |--- M2 -----|            |            |            |
   |            | AWS Infra (Jess)        |            |            |
   |            |            |--- M3 -----|            |            |
   |            |            | Distributed (Both)      |            |
   |            |            |            |--- M4 -----|            |
   |            |            |            | Frontend (Sam)          |
   |            |            |            |            |--- M5 -----|
   |            |            |            |            | Experiments (Both)
   v            v            v            v            v            v
 Start        MVP done     AWS deployed  Pipeline     Frontend +   Experiments
 posting      locally      + reachable   on AWS       feedback     + write-up
```

---

## Task Breakdown by Milestone

### M1: MVP Pipeline — Sam (Mar 25 - Mar 28)

Get a working 6-stage pipeline running locally. Analyze trending content, generate scripts, simulate audience voting, personalize output.

| # | Title | Size | Status | Completed |
|---|-------|------|--------|-----------|
| #16 | Project scaffolding + Pydantic models | S | Done | Mar 27 |
| #17 | Provider interface + Gemini implementation | S | Done | Mar 27 |
| #18 | S1 analyze + S2 aggregate (MapReduce Cycle 1) | M | Done | Mar 27 |
| #19 | S3 generate + S4 vote + S5 rank (MapReduce Cycle 2) | M | Done | Mar 27 |
| #20 | S6 personalize + local runner + CLI | M | Done | Mar 27 |
| #21 | Download dataset + first real pipeline run | M | Done | Mar 27 |
| #22 | Generate + post first video | M | Suspended | -- |
| #60 | Add Kimi (Moonshot) as default reasoning provider | M | Done | Mar 28 |

> M1 status: 7/8 issues closed. #22 suspended (video generation depends on external API availability).

### M2: AWS Infrastructure — Jess (Mar 28 - Apr 4)

Deploy all AWS services via Terraform. Goal: ALB URL returns 200 from /api/health.

| # | Title | Size | Status | Completed |
|---|-------|------|--------|-----------|
| #23 | Terraform project + VPC + IAM roles | M | Done | Mar 28 |
| #24 | S3 bucket + DynamoDB tables | S | Done | Mar 28 |
| #25 | ElastiCache Redis + ECR repository | S | Done | Mar 28 |
| #26 | ECS Fargate + ALB (API service) | L | Done | Mar 28 |
| #27 | ECS Fargate (Celery worker service) | M | Done | Mar 28 |
| #28 | Lambda function for S7 video generation | M | Done | Mar 28 |

> M2 status: 6/6 issues closed. All infrastructure deployed.

### M3: Distributed Pipeline — Both (Apr 4 - Apr 8)

Wire up API, Celery workers, orchestrator, and distributed systems features.

| # | Title | Owner | Size | Status |
|---|-------|-------|------|--------|
| #29 | FastAPI routes + infra clients (Redis, S3, DynamoDB) | Both | L | Planned |
| #30 | Celery tasks + orchestrator state machine | Jess | L | Planned |
| #31 | Rate limiter + SETNX cache | Jess | M | Planned |
| #32 | SSE streaming + checkpoint recovery | Both | M | Planned |
| #33 | Multi-user validation (3 concurrent runs) | Both | M | Planned |

### M4: Frontend + Feedback Loop — Sam (Apr 8 - Apr 11)

Astro frontend with React islands for real-time pipeline visualization.

| # | Title | Size | Status |
|---|-------|------|--------|
| #34 | Astro project scaffold + Cloudflare Pages deploy | S | Planned |
| #35 | Create page (input form + model selection) | M | Planned |
| #36 | Pipeline visualizer (SSE-connected React island) | L | Planned |
| #37 | Voting animation (100-avatar React island) | L | Planned |
| #38 | Results page + video player | M | Planned |
| #39 | Performance tracking page + feedback API | M | Planned |
| #40 | Insights dashboard + runs page | M | Planned |

### M5: Experiments + Write-up — Both (Apr 11 - Apr 15)

Run three distributed systems experiments and collect data for the course write-up.

| # | Title | Owner | Size | Status |
|---|-------|-------|------|--------|
| #41 | Experiment 1: Multi-tenant backpressure | Both | L | Planned |
| #42 | Experiment 2: Failure recovery + run isolation | Both | L | Planned |
| #43 | Experiment 3: Cross-user cache concurrency | Both | L | Planned |

### Cross-cutting

| # | Title | Owner | Size | Status | Completed |
|---|-------|-------|------|--------|-----------|
| #44 | CI/CD pipeline (GitHub Actions) | Jess | S | Done | Mar 28 |
| #50-55 | Pipeline quality polish (prompts, models, personas) | Sam | S-M | Open | -- |

---

## Who Is Doing What

| Team Member | Issues | Scope |
|-------------|--------|-------|
| **Sam** | 14 | M1 pipeline stages (#16-#22, #60), M4 frontend (#34-#40) |
| **Jess** | 9 | M2 AWS infrastructure (#23-#28), M3 orchestrator (#30, #31), CI/CD (#44) |
| **Both** | 6 | M3 integration (#29, #32, #33), M5 experiments (#41, #42, #43) |

**Total tracked issues:** 29 (+ 6 polish issues)

**Size breakdown:** 6 Small (half day), 15 Medium (1 day), 8 Large (2-3 days)

---

## Critical Path

The longest dependency chain determines the project deadline:

```
#23 --> #25 --> #26 --> #29 --> #30 --> #31 --> #33 --> #41/#42/#43
 VPC    Redis   ECS     API    Celery   Rate    Multi    Experiments
                                        limit   user
```

If any issue on this chain slips, experiments get compressed. Everything else has float.

Key dependency relationships:
- M3 cannot start until M2 (AWS) is deployed and M1 (pipeline stages) is complete
- M4 frontend scaffold (#34) has no backend dependency — can start early
- M5 experiments require the full distributed system (M3) to be operational

---

## AI Usage in Development

### How AI tools were used

| Area | Tool | What it did |
|------|------|-------------|
| **Architecture design** | Claude Code | Designed 7-stage MapReduce pipeline, wrote architecture spec, created data models |
| **Spec writing** | Claude Code | Drafted all 29 GitHub issues with acceptance criteria, dependency graphs, size estimates |
| **Code generation** | Claude Code (Shannon) | Implemented pipeline stages, provider interfaces, Pydantic models, CLI runner |
| **Code review** | Claude Code | Automated review on every PR; catches type errors, missing edge cases, style issues |
| **CI/CD** | GitHub Actions | Automated lint (ruff) + test (pytest) on every push |
| **Research** | Claude Code | Analyzed viral content psychology for persona design, evaluated dataset options (TikTok-10M vs Gopher-Lab transcripts) |
| **Debugging** | Claude Code | Diagnosed Gemini API intermittent 500s, implemented retry logic with exponential backoff |

### Cost-benefit assessment

**Time saved:**
- Architecture + spec phase completed in ~2 days instead of estimated 5
- Boilerplate code generation (models, interfaces, tests) saved ~1 day per milestone
- Automated PR review catches issues before human review, reducing review cycles

**Review overhead:**
- Every AI-generated PR requires human review — adds ~30 min per PR
- AI occasionally over-engineers solutions — need to simplify before merging
- Prompt iteration for pipeline stages required 3-4 rounds to get output quality right

**Net assessment:** AI accelerated the project by roughly 40%, primarily in the spec/scaffolding/review phases. Implementation still requires significant human judgment for prompt engineering and integration decisions.

---

## Current Status Summary (as of March 28, 2026)

| Milestone | Progress | Key Metrics |
|-----------|----------|-------------|
| **M1: MVP Pipeline** | 86% (6/7 closed, 1 suspended) | All 6 stages implemented + tested, Kimi provider integrated, first real pipeline run complete |
| **M2: AWS Infra** | 100% (6/6 closed) | Full Terraform stack: VPC, ECS, ALB, Redis, S3, DynamoDB, Lambda |
| **M3: Distributed** | 0% (0/5) | Not started — on schedule per timeline (starts Apr 4) |
| **M4: Frontend** | 0% (0/7) | Not started — on schedule per timeline (starts Apr 8) |
| **M5: Experiments** | 0% (0/3) | Not started — on schedule per timeline (starts Apr 11) |
| **CI/CD** | Done | GitHub Actions pipeline active |

**Overall numbers:**
- **Issues closed:** 14 of 29 (48%)
- **Test suite:** 45 tests passing
- **CI/CD:** Active on all PRs (ruff lint + pytest)
- **AI providers:** 2 integrated (Kimi for reasoning, Gemini for video generation)
- **Pipeline stages:** 6 of 7 implemented (S1 analyze, S2 aggregate, S3 generate, S4 vote, S5 rank, S6 personalize)

**Risk assessment:** M1 and M2 completed ahead of schedule. The critical path through M3 has adequate buffer. Primary risk is M3-to-M5 integration complexity — the distributed systems experiments depend on a fully operational multi-user pipeline.
