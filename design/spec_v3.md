# Project Spec — Pattern Learning & Crowd-Validated Content Generation for Short-Form Video

| | |
|---|---|
| **Authors** | Sam Wu · Jess |
| **Course** | CS6650 — Distributed Systems |
| **Version** | v3.1 — March 2026 (multi-user + all-AWS + feedback loop revision) |
| **Status** | Draft — under review |
| **Repo** | https://github.com/yangyang-how/flair2 |
| **Supersedes** | spec_v2.md (single-user, Railway) |

---

## What Changed in V3

V2 was designed for a single user running one pipeline at a time. V3 assumes **many concurrent users**, each running independent pipeline runs simultaneously. This changes why every distributed systems component exists:

| Component | V2 justification | V3 justification |
|-----------|------------------|------------------|
| ALB + multiple ECS instances | "Demonstrates horizontal scaling" | Required — concurrent users need concurrent API capacity |
| Celery task queue | "Distributes one user's 100 map tasks" | Required — isolates and schedules tasks across many concurrent pipeline runs |
| Redis rate limiter | "Prevents one pipeline from flooding the LLM" | Required — many users share one API key's quota |
| DynamoDB | Non-goal in v2 | Required — run metadata, performance tracking, queryable index |
| S3 | Not mentioned | Required — pipeline output files (results JSON, video mp4s), input dataset |
| Redis key namespacing | Not needed (one run at a time) | Required — concurrent runs must not collide |
| Feedback loop | Not in scope | Core feature — real video performance data improves pipeline over iterations |

V3 also moves all infrastructure to AWS (no Railway) to align with the course and showcase AWS skills.

V3 adds a **two-track development strategy**: an MVP track (built on V1 hackathon code) to start generating and posting videos immediately, and an infrastructure track to build the distributed AWS system in parallel. The feedback loop connects the two — real performance data from posted videos feeds back into the pipeline to improve script quality, prompt quality, and audience persona calibration.

---

## 1. Problem

Creators who want to make viral short-form videos currently do so by manually watching hundreds of top-performing videos, trying to intuit patterns, and then writing scripts by hand. This process is slow, subjective, and produces scripts that sound like copies rather than authentic content.

This system automates the pattern-extraction phase and the generation phase, while using a crowd-simulation voting step to surface the highest-potential content before personalizing it to the creator's own voice.

**Three output modes** — the system produces, for each top-ranked script:
1. **Video scripts** — personalized to creator's voice, for humans to shoot themselves
2. **Video prompts** — structured prompts ready for any AI video generator
3. **Generated videos** — 4–8 second AI-generated clips, on-demand per script (user picks which ones to generate — not all 10)

**The academic goal** is to build a multi-user distributed system on AWS infrastructure with two MapReduce cycles, observe real distributed systems phenomena (multi-tenant backpressure, partial failure isolation, cache concurrency across users), and produce measurable experimental results.

**The resume goal** is a portfolio piece demonstrating: distributed AI pipeline architecture on AWS, multi-tenant resource management, configurable multi-provider LLM integration, crowd-simulation evaluation, and a polished web frontend with real-time pipeline visualization.

---

## 2. Architecture

### 2.1 Two-Service Architecture

| Service | Stack | Deploy | Purpose |
|---------|-------|--------|---------|
| **Frontend** | Astro + React islands (TypeScript), Framer Motion | Cloudflare Pages | Input forms, pipeline visualization, voting animation, output display |
| **Backend** | Python 3.11+, FastAPI, Redis, Celery | AWS ECS Fargate + ALB | AI pipeline, worker coordination, LLM provider routing |
| **Redis** | Redis 7 | AWS ElastiCache (single node) | Shared state: task queues, checkpoints, rate limiter, cache, SSE events |
| **File storage** | S3 | AWS S3 | Pipeline output files (results JSON, video mp4s), input dataset |
| **Metadata & tracking** | DynamoDB | AWS DynamoDB (single-region, PAY_PER_REQUEST) | Run metadata, performance tracking, queryable index |
| **Video generation** | Lambda function | AWS Lambda | On-demand video generation (S7), bursty workload. Fallback to ECS workers if external API exceeds 15-min Lambda timeout. |

**Why Cloudflare Pages for frontend:** Instant deploy with preview URLs on every PR. AWS hosting (S3 + CloudFront) adds complexity without benefit for a static frontend. The frontend is not where we demonstrate AWS skills — the backend is.

**Why ALB + multiple ECS instances:** Multiple concurrent users each hold open SSE connections while their pipeline runs. A single API instance becomes the bottleneck under concurrent load. The ALB distributes incoming HTTP and SSE connections across ECS tasks. This is real horizontal scaling driven by real traffic, not a demonstration exercise.

**Why S3 for file storage:** Pipeline outputs are files — results JSON (~50KB) and video clips (~2-10MB). S3 is built for this: no size limits, dirt cheap, accessible from any ECS task or Lambda function. DynamoDB has a 400KB item size limit and can't store video files. S3 serves videos directly to the frontend via presigned URLs — no need to proxy through the API.

**Why DynamoDB for metadata:** S3 stores files but can't efficiently answer "list all runs for this session sorted by date" or "which videos performed best." DynamoDB provides the queryable index layer — run metadata, performance tracking, S3 pointers. Different tools for different access patterns.

**Why Lambda for S7:** Video generation is user-triggered, bursty, and expensive. Most of the time zero users are generating videos; occasionally several trigger at once. Lambda's pay-per-invocation model fits this pattern perfectly — no idle ECS containers burning money waiting for the rare video request. Estimated external API response time: 5-10 minutes (4-8s clips). If actual response times exceed Lambda's 15-minute limit during testing, fall back to ECS workers.

**Communication:** SSE (Server-Sent Events) for real-time pipeline status. The frontend opens an SSE connection when generation starts; the backend streams stage completion events and individual vote events for the voting animation.

### 2.2 Multi-User Model

Each user gets an independent pipeline run identified by a unique `run_id` (UUID). Multiple runs execute concurrently, sharing compute resources (ECS tasks, Celery workers) and LLM API quotas but isolated in state (Redis keys, DynamoDB records).

**User identity:** Session-based. Each browser session receives a unique session ID. Pipeline runs are associated with sessions. No login required — this is a course project, not a production SaaS.

**Run isolation:** All Redis keys are namespaced by `{run_id}`. A worker crash or failure in one user's pipeline does not affect any other user's pipeline. DynamoDB records are keyed by `run_id`.

**Security note:** Run IDs are UUIDs — guessing another user's run_id is computationally impractical. For a course project, this is sufficient. Production would add Cognito authentication.

### 2.3 Pipeline Overview

Seven stages, two MapReduce cycles, one sequential generation step, one style-injection step, one on-demand video step.

```
INPUT: Top 100 videos by engagement from dataset (see design/dataset-research.md)
       + creator voice profile (per user, per run)

┌─ MapReduce Cycle 1 ───────────────────────────────────────────┐
│  S1 MAP     100 videos  →  N workers  →  1 pattern per video  │
│  S2 REDUCE  N patterns  →  1 worker   →  pattern library      │
└───────────────────────────────────────────────────────────────┘

S3 SEQUENTIAL  pattern library  →  50 candidate scripts

┌─ MapReduce Cycle 2 ───────────────────────────────────────────┐
│  S4 MAP     100 simulated voters  →  N workers  →  top 5 each │
│  S5 REDUCE  votes  →  1 worker    →  ranked top 10 scripts    │
└───────────────────────────────────────────────────────────────┘

S6 STYLE INJECT + PROMPT GENERATION
   top 10 + creator voice profile  →  for each:
     a) personalized video script (text)
     b) AI video prompt (structured text)

S7 VIDEO GENERATION (on-demand, user-triggered, AWS Lambda)
   user selects 1-3 scripts  →  generate 4-8s video clip per selection

OUTPUT:
  - 10 personalized scripts with viral structure + authentic voice
  - 10 video prompts ready for AI generation
  - 1-3 generated video clips (only for scripts the user explicitly chose)
```

**Concurrency model:** When 5 users each start a pipeline, the system has 5 independent runs in flight. Celery workers pull tasks from any run's queue — whichever task is next. All 5 runs share the LLM API rate limit. S3 (sequential bottleneck) runs per-pipeline, not globally — each user's S3 blocks only their own pipeline.

### 2.4 Content Strategy: Structural Patterns vs Surface Trends

The pipeline's value depends on understanding what it can and cannot learn from data.

**Platforms actively punish imitation.** TikTok's 2025-2026 algorithm updates penalize "forced trend adoption," suppress copycat content, and use AI detection to identify unoriginal editing patterns. YouTube Shorts actively suppresses cross-platform reposts and penalizes high drop-off rates from stale hooks. Instagram deprioritizes reposted or duplicated material.

**Trend lifecycles are brutally fast.** A viral trend goes from emergence → peak → saturation → decline in 7-14 days. Hyper-viral challenges burn through the cycle in 48-72 hours. By the time any dataset captures a trending video's metrics, that trend is often already dead or saturated.

This means the pipeline must distinguish between three layers of content knowledge, each with a different decay rate:

| Layer | Example | Lifespan | Learn from |
|---|---|---|---|
| **Surface trends** | Specific sounds, dances, memes, challenges | Days to weeks | DON'T learn — too late by the time data exists, imitation is punished |
| **Structural patterns** | Hook types, pacing techniques, emotional arcs, reveal timing | Months to ~1-2 years | Historical datasets (one-time analysis in S1/S2) |
| **Platform meta** | What the algorithm currently rewards (originality? watch time? shares?) | Changes with algorithm updates | Our own posted video performance (feedback loop) |

**S1 must extract structural patterns, not surface trends.** Research shows 82% of videos exceeding 500K views follow one of four basic structures — same hook patterns, same pacing, same reveal timing — with only the topic changing. The structural mechanics are the transferable knowledge. The specific trends are not.

**S1 prompt guidance:**

| Extract (structural) | Do NOT extract (surface) |
|---|---|
| Hook type: question / shock / story / direct address | Specific sounds or audio tracks |
| Pacing pattern: fast start → slow middle → fast end | Specific dances or challenges |
| Pattern interrupt timing (e.g., shift at 40% mark) | Specific memes or references |
| Emotional arc: setup negative → resolve positive | Specific hashtags or trends |
| Retention mechanic: curiosity gap, open loop, payoff delay | Specific filters or effects |

**Structural patterns aren't truly timeless — they're cyclical.** Like fashion colors, they rotate in and out of effectiveness. Fast-cut editing dominated 2020-2022, saturated, and gave way to slower "authentic" content in 2024-2025. Eventually fast cuts will feel fresh again. The patterns themselves don't disappear — they move through cycles of rising → peak → saturation → dormancy → revival. This is why the feedback loop matters: not to detect trends, but to detect which structural patterns are currently in their effective phase for a given creator.

### 2.5 Performance Feedback Loop

The feedback loop is **pipeline output calibration, not trend detection.**

Our own posted videos (~15-20 over 3 weeks) are far too small a sample to detect macro trend cycles — platforms process billions of signals for that. What our data *can* do is calibrate the pipeline's output quality for a specific creator.

```
┌──────────────────────────────────────────────────────────────────┐
│                                                                  │
│  Pipeline  ──►  Scripts  ──►  Videos  ──►  Post to  ──►  Collect │
│  (S1-S7)       + prompts     (S7)        social        metrics   │
│                                           media                  │
│     ▲                                                     │      │
│     │              Pipeline calibration data:             │      │
│     │              - Which of OUR scripts performed?      │      │
│     │              - Were the committee's predictions     │      │
│     │                accurate?                            │      │
│     │              - Which prompt templates produce       │      │
│     │                better output?                       │      │
│     │                                                     │      │
│     └──── Calibrate pipeline output quality ◄─────────────┘      │
│            (NOT trend detection)                                  │
└──────────────────────────────────────────────────────────────────┘
```

**What the feedback loop does (with ~20 data points):**

| Purpose | How it works | Example |
|---------|-------------|---------|
| **Script quality ranking** | Compare predicted rank (S4/S5) vs actual performance | "Committee predicted Script B as #1, but Script C outperformed it 10:1 — recalibrate persona evaluation criteria" |
| **Pattern effectiveness** | Track which structural patterns produce better results for this creator | "Shock hooks are outperforming question hooks for this creator's audience — weight toward shock hooks" |
| **Prompt template refinement** | A/B test different prompt strategies via real results | "Prompt template X consistently produces higher-engagement scripts than template Y" |
| **Creator-specific personalization** | Learn what works for THIS voice on THIS platform | "This creator's audience responds to direct address over narration — adjust S6 style injection" |

**What the feedback loop does NOT do (would need millions of data points):**

- Detect macro trend cycles
- Predict which structural patterns are rising vs declining globally
- Forecast algorithm changes
- Compete with platform-level recommendation systems

**Data collection:** Manual entry initially. Users submit performance metrics via a web form or API endpoint after posting videos and observing results. Automation (TikTok/YouTube API integration) is a future enhancement, not required for the course project.

**Data storage:** Performance metrics are stored in DynamoDB (see Section 5.5), linked to the pipeline run and script that generated the video. Historical performance data is queried at the start of each new pipeline run and injected into LLM prompts.

### 2.6 Two-Track Development Strategy

The feedback loop requires real performance data, which requires real posted videos, which requires a working pipeline. Waiting until the full distributed system is built to start posting means losing weeks of calibration data. Therefore:

**Track 1 — MVP Pipeline (immediate priority)**
- Built on the V1 hackathon codebase (`gemini-social-asset`)
- Single-user, runs locally, end-to-end: input → scripts → videos
- Goal: start generating and posting videos within days
- No AWS infrastructure needed — runs on a laptop
- Output: daily posted videos + manual performance data collection

**Track 2 — Distributed Infrastructure (parallel)**
- Full multi-user AWS architecture (ECS, ALB, ElastiCache, S3, DynamoDB, Lambda)
- All distributed systems features (MapReduce, rate limiting, checkpoints, experiments)
- Performance tracking endpoints and feedback loop integration
- Goal: production system ready by end of course

**Timeline:**
- **Week 1:** MVP pipeline generating videos daily. Infrastructure design finalized.
- **Weeks 2-3:** Infrastructure built. MVP performance data (~15-20 videos) available to feed into the distributed pipeline.
- **Week 3+:** Distributed system running with real feedback data. Experiments executed. Write-up includes measurable improvement from the feedback loop.

**Work split:** Sam focuses on frontend + MVP video generation. Jess focuses on infrastructure. Both contribute to backend pipeline logic. Formal task assignment happens after spec is finalized and a backlog is created.

### 2.7 Module Responsibilities

| **Stage** | Responsibility | Provider Group |
|-----------|---------------|---------------|
| **S1 Analyze (Map)** | Call LLM once per video. Extract **structural** patterns only: hook type (question/shock/story/direct address), pacing pattern, emotional arc, pattern interrupt timing, retention mechanics. Do NOT extract surface trends (specific sounds, dances, memes). Output: JSON pattern object per video. | Reasoning |
| **S2 Aggregate (Reduce)** | Merge N pattern objects into a deduplicated pattern library. Output: ranked pattern list with frequency counts. | Algorithmic (no LLM) |
| **S3 Generate** | Sequential. For each top pattern, generate a script variant. 50 scripts total. No parallelism — deliberate bottleneck for Amdahl's Law observation. | Reasoning |
| **S4 Vote (Map)** | Simulate 100 viewer personas, each evaluating all 50 candidate **scripts** (text only — not prompts or videos) and predicting their top 5 picks. One LLM call per persona-worker. | Reasoning |
| **S5 Rank (Reduce)** | Aggregate votes into a ranked leaderboard. Output: top 10 scripts by vote score. | Algorithmic (no LLM) |
| **S6 Personalize + Prompt** | For each of top 10: (a) rewrite script to match creator voice, (b) generate structured video prompt. All text — no video generation here. | Reasoning |
| **S7 Generate Video (on-demand)** | User selects 1-3 scripts from results and explicitly triggers video generation. Runs on AWS Lambda. One 4-8s clip per selected script. Not part of the automated pipeline. | Video |
| **Redis** | Shared state for all workers across all runs. Task queues (BRPOP/RPUSH), result storage, token bucket rate limiter, SETNX cache lock. All keys namespaced by `{run_id}` except shared caches. | — |
| **S3** | File storage for pipeline outputs (results JSON, video mp4s) and input dataset. Accessible from any ECS task or Lambda via presigned URLs. | — |
| **DynamoDB** | Run metadata index + performance tracking. Written at end of S6 (metadata) and after posting (performance metrics). Keyed by `run_id`. | — |
| **Orchestrator** | Starts workers, monitors stage completion per run, streams SSE events to the correct user's frontend connection, handles timeouts. | — |

### 2.8 LLM Provider Architecture

The system uses a **two-group configurable provider model**, selectable from the web UI before each pipeline run.

**Group 1 — Reasoning (everything except video)**
Handles: text analysis (S1), script generation (S3), persona evaluation (S4), style injection (S6a), video prompt writing (S6b), ingesting uploaded materials, processing user inputs.

| Provider | Notes |
|----------|-------|
| Kimi 2.5 | Sam's subscription. Strong at text + image understanding. Primary choice. |
| Google Gemini | Good fallback. Free tier available. |
| OpenAI GPT-4o-mini | Cost-effective. Good structured output. |
| [extensible] | Any provider that implements the interface can be added. |

**Group 2 — Video generation (expensive, use deliberately)**
Handles: generating 4-8 second video clips (S7) only.

| Provider | Notes |
|----------|-------|
| Seedance 2.0 (via PiAPI/ModelsLab) | Best motion quality + multimodal input. $0.50-3 per clip. |
| Google Veo | Higher resolution. Pricing varies. |
| [extensible] | Any video API that implements the interface can be added. |

**UI flow:** On the `/create` page, before starting the pipeline, the user selects:
1. Reasoning model (dropdown: Kimi 2.5 / Gemini / GPT-4o-mini)
2. Video model (dropdown: Seedance 2.0 / Google Veo / Skip video generation)

The "Skip video generation" option hides the "Generate Video" buttons on the results page entirely — the user gets scripts + prompts only, at zero video cost.

**Provider interface:**
```python
class ReasoningProvider(Protocol):
    async def generate_text(self, prompt: str, schema: dict | None = None) -> str: ...
    async def analyze_content(self, content: bytes, prompt: str) -> str: ...

class VideoProvider(Protocol):
    async def generate_video(self, prompt: str, duration: int = 6) -> bytes: ...
    async def check_status(self, job_id: str) -> dict: ...
```

All providers implement the appropriate interface. The orchestrator reads the user's selection from the pipeline request, not from a static config file. Different runs can use different providers without restarting the backend.

**Multi-user rate limiting:** All users share a single API key per provider. The token bucket rate limiter operates globally per provider — not per user, not per run. This reflects reality: the API key has one rate limit regardless of who triggered the call. When the bucket is empty, all users' workers wait equally.

---

## 3. Frontend

### 3.1 Pages

| Page | What It Shows |
|------|-------------|
| **/** | Landing — project description, start button |
| **/create** | Input form: upload creator_profile.json or fill in fields (tone, vocabulary, catchphrases, topics_to_avoid). Model selection: Reasoning model dropdown (Kimi 2.5 / Gemini / GPT-4o-mini) + Video model dropdown (Seedance 2.0 / Google Veo / Skip video). Start pipeline button. |
| **/pipeline/{run_id}** | Real-time pipeline visualization for a specific run. Seven stages shown as connected nodes. Each stage animates as it processes (progress bar, item count). SSE-powered. |
| **/vote/{run_id}** | Voting visualization. 100 simulated audience members appear as avatars. Each evaluates the 50 candidate **scripts** and casts votes in real-time (animated). Votes aggregate into a leaderboard showing the top 10 scripts. This is the visual centerpiece. |
| **/results/{run_id}** | Final output display. Tab view: Scripts / Video Prompts. Each of the top 10 results shown with the creator's personalized version alongside the original. Each script has a "Generate Video" button — user picks 1-3 to generate, video appears when ready (async, may take 1-3 minutes). |
| **/runs** | List of the current session's pipeline runs with status (running / completed / failed). Links to each run's pipeline/results page. |
| **/track/{run_id}** | Performance tracking form. For each posted video from this run: enter platform, post URL, and metrics (views, likes, comments, shares, watch time). Manual entry for now — automation is a future enhancement. |
| **/insights** | Dashboard showing performance data across all tracked videos. Which script patterns perform best? How has pipeline output quality improved over iterations? Comparison of committee predictions vs actual performance. |

### 3.2 Interactive Components (React Islands)

Only three components need React hydration — the rest is static Astro:

1. **PipelineVisualizer** — SSE-connected, shows stage progress in real-time, Framer Motion transitions between stages
2. **VotingAnimation** — 100 avatar grid, each avatar animates when casting a vote, leaderboard updates live, Framer Motion for vote movements
3. **VideoPlayer** — Plays generated 4-8s clips on the results page. Shows loading state while video generates (1-3 min). Only appears for scripts where user clicked "Generate Video."

---

## 4. Data Flow

| **Input** | Tsinghua/Kuaishou 10K user preference dataset. Use first 100 videos by engagement rank. |
|---|---|
| **S1 → S2** | Redis: `result:s1:{run_id}:{video_id}` keys, each a JSON blob with hook, pacing, structure fields. |
| **S2 → S3** | Redis: `pattern_library:{run_id}`, a JSON array sorted by frequency. |
| **S3 → S4** | Redis: `scripts:candidates:{run_id}`, 50 JSON script objects. |
| **S4 → S5** | Redis: `result:s4:{run_id}:{persona_id}`, each a list of 5 script IDs. SSE events streamed to frontend per vote. |
| **S5 → S6** | Redis: `top_scripts:{run_id}`, array of top 10 script IDs + scores. |
| **S6 → S3 + DynamoDB** | Results JSON written to `s3://bucket/{run_id}/results.json`. Run metadata written to DynamoDB. Also written to Redis at `results:final:{run_id}` for immediate SSE delivery. |
| **S7 (on-demand)** | User triggers via `/api/video/generate`. Lambda generates clip. Video stored at `s3://bucket/{run_id}/videos/{script_id}.mp4`. Status updated in DynamoDB. Frontend gets presigned URL for playback. |
| **Creator Voice** | Input via web form or file upload: `creator_profile.json`. Fields: tone, vocabulary, catchphrases, topics_to_avoid. |
| **Performance data** | Manual entry via `/track/{run_id}` form or `POST /api/performance`. Stored in DynamoDB `video_performance` table. Queried at start of next pipeline run and injected into S3/S4/S6 prompts. |
| **Feedback → Pipeline** | At pipeline start, query DynamoDB for historical performance data. Top-performing and worst-performing scripts (with their patterns, prompts, and metrics) are included in LLM prompts for S3, S4, and S6. |

### 4.1 Cross-User Cache

S1 pattern analysis is deterministic for a given video + prompt combination. If User A and User B both analyze the same video, the result is identical. The shared cache key `cache:s1:{video_id}:{prompt_hash}` has **no run_id prefix** — it is shared across all users.

This means the second user's pipeline skips the LLM call entirely and reads from cache. This is both a cost optimization and a distributed systems talking point: shared immutable caches across tenants.

The SETNX lock ensures exactly one LLM call per unique input, regardless of how many users trigger it concurrently.

---

## 5. API Contracts

### 5.1 LLM Provider Usage

| **Reasoning model** | User-selected per run (Kimi 2.5, Gemini, or GPT-4o-mini) |
|---|---|
| **Video model** | User-selected per run (Seedance 2.0, Google Veo, or skip) |
| **Rate limit** | Global token bucket in Redis per provider — shared across all users |
| **S1 prompt output** | JSON: `{ hook_type, pacing, structure, engagement_triggers[] }` |
| **S4 prompt output** | JSON: `{ top_5_script_ids: [id, id, id, id, id] }` |
| **S6a output** | String: rewritten script text |
| **S6b output** | JSON: structured video prompt |
| **S7 output** | Binary: video file (mp4, 4-8s) |
| **Total reasoning calls per run (est.)** | ~260 (100 analyze + 50 generate + 100 vote + 10 personalize/prompt) |
| **Total video calls per run (est.)** | 1-3 (user-triggered, on demand) |

### 5.2 Redis Key Schema

```
# ── Per-run state (namespaced by run_id) ──────────────────────
run:{run_id}:status            STRING — pipeline status (pending/running/completed/failed)
run:{run_id}:config            STRING — JSON {reasoning_model, video_model, creator_profile}
task:s1:{run_id}               LIST   — video IDs pending S1 analysis (BRPOP queue)
result:s1:{run_id}:{video_id}  STRING — JSON pattern object from S1
pattern_library:{run_id}       STRING — JSON array, written by S2
scripts:candidates:{run_id}    STRING — JSON array, 50 scripts from S3
task:s4:{run_id}               LIST   — persona IDs pending S4 voting (BRPOP queue)
result:s4:{run_id}:{persona}   STRING — JSON list of 5 script IDs
top_scripts:{run_id}           STRING — JSON array of top 10 {id, score}
results:final:{run_id}         STRING — JSON array of 10 {script, prompt}
results:video:{run_id}:{id}    STRING — JSON {status, video_url} — written by S7
checkpoint:{run_id}:{stage}    STRING — last completed task index for recovery
sse:events:{run_id}            LIST   — SSE event queue for this run's frontend

# ── Global (shared across all runs) ───────────────────────────
cache:{provider}:{prompt_hash} STRING — SETNX-protected shared LLM result cache
ratelimit:{provider}           STRING — token bucket counter (expires per window)

# ── Session tracking ──────────────────────────────────────────
session:{session_id}:runs      LIST   — run_ids belonging to this session
```

### 5.3 Backend API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/pipeline/start` | POST | Start pipeline with creator profile + model selections. Returns `{ run_id }`. Body: `{ creator_profile, reasoning_model, video_model }` |
| `/api/pipeline/status/{run_id}` | GET (SSE) | Stream pipeline events for a specific run |
| `/api/pipeline/results/{run_id}` | GET | Get final results from DynamoDB (10 scripts + prompts) |
| `/api/runs` | GET | List current session's pipeline runs with status |
| `/api/video/generate` | POST | User-triggered: generate video for a specific script. Body: `{ run_id, script_id }`. Invokes Lambda. |
| `/api/video/status/{run_id}/{job_id}` | GET | Poll video generation status (processing / complete / failed) |
| `/api/performance` | POST | Submit performance metrics for a posted video. Body: `{ run_id, script_id, platform, post_url, metrics: { views, likes, comments, shares, watch_time_avg, completion_rate } }` |
| `/api/performance/{run_id}` | GET | Get all performance data for a run's posted videos |
| `/api/insights` | GET | Aggregated insights across all tracked videos — top patterns, prediction accuracy, improvement over time |
| `/api/providers` | GET | List available reasoning and video providers (for frontend dropdowns) |
| `/api/health` | GET | Health check |

### 5.4 S3 Bucket Structure

```
s3://flair2-pipeline/
  dataset/
    videos/                          ← Kuaishou input dataset (shared)
  runs/
    {run_id}/
      config.json                    ← run config (models, creator profile)
      results.json                   ← 10 scripts + 10 prompts (~50KB)
      videos/
        {script_id}.mp4              ← generated video clips (~2-10MB each)
```

**Access patterns:**
- Write results at end of S6 → `PutObject`
- Write video from Lambda → `PutObject`
- Read results for display → `GetObject` or presigned URL
- Play video in frontend → presigned URL (temporary, time-limited link — frontend plays directly from S3, no API proxy)

### 5.5 DynamoDB Schema

**Table: `pipeline_runs`** — run metadata and S3 pointers

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `run_id` | String (UUID) | Partition key | Unique pipeline run identifier |
| `session_id` | String | GSI partition key | Session that owns this run |
| `status` | String | — | pending / running / completed / failed |
| `config` | Map | — | `{ reasoning_model, video_model, creator_profile }` |
| `s3_results_key` | String | — | S3 key for results.json |
| `s3_video_keys` | Map | — | `{ script_id: s3_key }` for generated videos |
| `created_at` | String (ISO 8601) | GSI sort key | Timestamp |
| `completed_at` | String (ISO 8601) | — | Timestamp (null until complete) |

**Access patterns:**
- Get run by `run_id` → `GetItem` (partition key)
- List runs by session → `Query` on GSI (`session_id`, sorted by `created_at`)
- Write metadata at end of S6 → `UpdateItem`
- Write video S3 pointer from Lambda → `UpdateItem`

**Table: `video_performance`** — real-world performance tracking for feedback loop

| Attribute | Type | Key | Description |
|-----------|------|-----|-------------|
| `run_id` | String (UUID) | Partition key | Which pipeline run generated this video |
| `script_id` | String | Sort key | Which script this video came from |
| `platform` | String | — | tiktok / youtube / instagram |
| `post_url` | String | — | Link to the actual post |
| `posted_at` | String (ISO 8601) | — | When it was posted |
| `metrics_updated_at` | String (ISO 8601) | — | Last time metrics were refreshed |
| `views` | Number | — | Total views |
| `likes` | Number | — | Total likes |
| `comments` | Number | — | Total comments |
| `shares` | Number | — | Total shares |
| `watch_time_avg` | Number | — | Average watch time in seconds |
| `completion_rate` | Number | — | % of viewers who watched to end (0-100) |
| `script_pattern` | Map | — | Copy of the script's pattern metadata (hook type, pacing, etc.) for correlation analysis |
| `committee_rank` | Number | — | What rank the S4/S5 committee predicted for this script |

**Access patterns:**
- Get performance by run + script → `GetItem` (partition + sort key)
- List all tracked videos for a run → `Query` (partition key)
- Scan for top performers across all runs → `Scan` with filter (acceptable at small scale — ~20-60 records total over the project lifetime)
- Feed into next pipeline run → query recent performance data, sort by views, inject top/bottom performers into prompts

Single-region, eventual consistency for both tables. Acceptable because data is written once and read later, with no concurrent writes to the same record.

---

## 6. Failure Modes & Handling

| **Failure** | Handling Strategy |
|---|---|
| **LLM rate limit hit (any provider)** | Global token bucket limiter in Redis prevents proactively. All users share the bucket. If still received: exponential backoff with jitter, max 3 retries. |
| **Worker crash mid-stage** | Checkpoint written to Redis after each task, scoped to `{run_id}`. On restart, worker reads `checkpoint:{run_id}:{stage}` and resumes. Other users' pipelines are unaffected. |
| **LLM returns invalid JSON** | JSON parse with try/except. On failure: retry once with stricter prompt. On second failure: skip item, log error, continue pipeline. |
| **Redis connection lost** | Workers retry connection with backoff. If Redis down > 30s: all in-flight pipelines halt, SSE error events sent to all connected frontends. |
| **S3 bottleneck timeout** | S3 is sequential per-run by design. If exceeds 10 min for one run: reduce to top 20 patterns, log truncation. Other runs are unaffected. |
| **Video generation timeout (Lambda)** | Lambda timeout set to 5 min. If exceeded: mark as failed, user can retry. Return script + prompt without video. |
| **Video generation fails** | Fallback to alternate provider. If both fail: deliver script + prompt without video. Log which provider failed. |
| **LLM API down (any provider)** | Try fallback provider. If all providers down: fail fast after 3 consecutive failures, save checkpoint, send error to frontend. Affects all users equally. |
| **Empty dataset** | Validate input at startup. If < 10 videos: halt with descriptive error before any API calls. |
| **Frontend loses SSE connection** | Auto-reconnect with exponential backoff. On reconnect, fetch current stage from `/api/pipeline/status/{run_id}`. No state lost — all state is in Redis. |
| **DynamoDB write fails** | Retry with backoff. Results remain in Redis as fallback. Alert in logs. |
| **Concurrent runs overload workers** | Celery workers process tasks FIFO across all runs. Under heavy load, each run takes longer but none are starved. Rate limiter prevents LLM API overload regardless of run count. |

---

## 7. Experiments

### Experiment 1 — Multi-Tenant Backpressure Under Load

| **Concept** | Flow control — token bucket rate limiting under multi-tenant contention |
|---|---|
| **Problem** | Multiple concurrent users share one LLM API key. Without rate control, concurrent pipeline runs flood the endpoint, triggering cascading 429 errors for all users. |
| **Setup** | Start K concurrent pipeline runs (K = 1, 3, 5, 10) each running S1 with N workers. Two conditions: (a) no rate limiter, (b) global Redis token bucket limiter shared across all runs. |
| **Measure** | Requests/min actually sent, error rate, per-run completion time, fairness (variance in completion time across runs). |
| **Expected** | No limiter: error rate spikes at K ≥ 3, some runs starved by retries. With limiter: throughput plateaus near API limit, all runs complete with similar latency, near-zero errors. |
| **Success criterion** | Limiter condition produces < 1% error rate at K=10. Completion time variance across runs < 20% (fairness). |
| **V3 improvement over V2** | V2 simulated concurrency with workers from one run. V3 measures real multi-tenant contention — fundamentally different failure mode (one user's retries can starve another). |

### Experiment 2 — Partial Failure Recovery with Run Isolation

| **Concept** | Fault tolerance — checkpoint-based recovery + run isolation |
|---|---|
| **Problem** | Worker crash at task 37 of 100 wastes 36 completed tasks without checkpointing. In multi-user, a crash must not affect other users' runs. |
| **Setup** | Start 3 concurrent pipeline runs. Kill a worker processing Run A's task at 25%, 50%, 75% completion. Observe: (a) does Run A recover via checkpoint? (b) are Runs B and C unaffected? |
| **Measure** | Run A: recovery time, redundant API calls, output correlation with full run. Runs B and C: completion time delta vs baseline (should be zero). |
| **Expected** | Checkpoint recovery is O(1) for Run A. Runs B and C complete with < 5% latency impact. |
| **Success criterion** | Checkpoint resume saves > 40% of API calls vs full restart. Other runs' completion times within 5% of no-crash baseline. |
| **V3 improvement over V2** | V2 only measured single-run recovery. V3 proves run isolation — a crash in one tenant doesn't cascade to others. |

### Experiment 3 — Cross-User Cache Concurrency

| **Concept** | Atomicity — SETNX vs naive GET/SET, with cross-user cache sharing |
|---|---|
| **Problem** | Multiple users may analyze the same videos simultaneously. Without atomic cache operations, duplicate LLM calls waste money and may produce inconsistent cached values. |
| **Setup** | Start K concurrent pipeline runs (K = 2, 5, 10) all analyzing the same 100 videos. Condition A: naive GET then SET. Condition B: atomic SETNX. |
| **Measure** | Total LLM calls (should be 100 with SETNX regardless of K), duplicate calls per cache key, total API cost, consistency of cached values across runs. |
| **Expected** | SETNX: exactly 100 LLM calls regardless of K (one per video, shared across all users). Naive: duplicates proportional to K. |
| **Success criterion** | SETNX produces exactly 1 LLM call per cache key across K=10 concurrent runs (100 total, not 1000). |
| **V3 improvement over V2** | V2 tested cache concurrency within one run (50 workers, same user). V3 tests across users — demonstrates that shared immutable caches reduce cost linearly with user count. |

---

## 8. Success Criteria

- Given 100 input videos, S1 produces exactly 100 pattern objects with no missing fields.
- S2 produces a non-empty pattern library with at least 3 distinct pattern types.
- S3 produces exactly 50 candidate scripts without halting.
- S4 produces votes from exactly 100 simulated personas, with SSE events visible in the frontend voting animation.
- S5 produces a ranked top-10 list with scores attached.
- S6 produces 10 final results, each containing: personalized script + video prompt.
- S6 writes results to S3 and metadata to DynamoDB. Results are readable after Redis restart.
- Video generation (S7) successfully produces a clip via Lambda, stored in S3, playable via presigned URL.
- Full pipeline (S1–S6) completes in under 60 minutes with 10 workers per run.
- **3 concurrent pipeline runs complete without interfering with each other.**
- **A worker crash in one run does not affect other concurrent runs.**
- All three experiments produce data sufficient for a results table.
- Pipeline survives a simulated worker crash without manual intervention.
- Frontend displays real-time pipeline progress and voting animation.
- LLM provider can be selected from the web UI per run without restarting the backend.
- Pipeline runs persist in S3 + DynamoDB and are retrievable after completion.
- **Performance metrics can be submitted via the tracking form and are stored in DynamoDB.**
- **At least one pipeline run uses historical performance data in its prompts, demonstrating the feedback loop.**
- **MVP pipeline generates at least 15 posted videos with tracked performance data before the final presentation.**

---

## 9. Non-Goals

- No automated social media API integration — performance data is entered manually. Automation (TikTok/YouTube API) is a future enhancement.
- No real TikTok/Kuaishou API for video input — data comes from the research dataset only.
- No relational database — file storage in S3, metadata in DynamoDB, ephemeral pipeline state in Redis.
- No auto-scaling — ECS task count and ElastiCache node size are fixed for the course project. (Production would add ECS auto-scaling policies and ElastiCache scaling.)
- No user authentication — session-based identity only. Production would add AWS Cognito.
- Not polishing the script → prompt → video quality funnel beyond what the feedback loop naturally improves. Manual prompt engineering optimization is out of scope.
- No fair scheduling between users — single shared Celery queue, FIFO. Noted as a limitation. Production would add per-user priority queuing.

---

## 10. Tech Stack

| **Component** | **Technology** | **Why** |
|---|---|---|
| Backend language | Python 3.11+ | Industry standard for AI services, resume signal |
| Frontend language | TypeScript (Astro + React) | Type safety, Astro for static perf, React for interactivity |
| Reasoning LLM | Kimi 2.5, Google Gemini, OpenAI GPT-4o-mini | User-selectable per run via provider interface |
| Video generation | Seedance 2.0 via PiAPI, Google Veo | User-selectable per run, or skip |
| Coordination | Redis 7 (AWS ElastiCache) | Task queues, checkpoints, rate limiter, cache, SSE events |
| File storage | AWS S3 | Pipeline output files (results, videos), input dataset |
| Metadata & tracking | AWS DynamoDB | Run metadata, performance tracking. PAY_PER_REQUEST. |
| Task queue | Celery (backed by Redis) | Async pipeline execution, retry, monitoring |
| Backend framework | FastAPI | Async-native, OpenAPI docs, Pydantic integration |
| Frontend framework | Astro + React islands, Framer Motion | Small bundle, interactive where needed |
| Backend deploy | AWS ECS Fargate + ALB | Horizontal scaling, no server management |
| Video compute | AWS Lambda | Pay-per-invocation for bursty S7 workload |
| Frontend deploy | Cloudflare Pages | Instant deploy, preview URLs per PR |
| Testing | pytest (backend) | Backend coverage, mocked AI APIs |
| Linting | ruff (backend) | Fast, comprehensive Python linting |
| CI | GitHub Actions | Lint + test on every push |
| Infra-as-code | Terraform | Reproducible AWS infrastructure |
| Dataset | Tsinghua/Kuaishou 10K user preference dataset | Academic research dataset |

---

## 11. AWS Services Showcased

| **Service** | **Purpose in Project** | **Distributed Systems Concept** |
|---|---|---|
| ECS Fargate | Backend API + Celery workers | Horizontal scaling, container orchestration |
| Application Load Balancer | Distribute requests across ECS tasks | Load balancing, health checks |
| ElastiCache (Redis) | Shared state, task queues, caching | Coordination, atomicity (SETNX), rate limiting |
| S3 | Pipeline output files, video storage, dataset | Object storage, presigned URLs |
| DynamoDB | Run metadata, performance tracking | CAP theorem (eventual consistency), single-key access patterns |
| Lambda | On-demand video generation (S7) | Serverless compute, pay-per-invocation vs always-on containers |
| CloudWatch | Logging and metrics from all services | Observability, structured logging with run_id correlation |
| IAM | Least-privilege roles per service | Security, principle of least privilege |

---

## 12. Open Questions

*Resolve these before writing code:*

1. How will we structure the `creator_profile.json`? What fields are required vs. optional? (The web form needs to match.)
2. ~~What does the Kuaishou dataset contain?~~ **Resolved:** Kuaishou datasets (KuaiRec, etc.) are recommender system datasets with no video content — unsuitable. Replaced with Tsinghua ShortVideo (transcripts + features) and TikTok-10M (captions + engagement). See `design/dataset-research.md`.
3. Kimi 2.5 rate limits — what are they? Confirm before Experiment 1 setup.
4. Seedance 2.0 API pricing via PiAPI — what's the cost per 4-8s clip? Budget for 1-3 clips per run × N concurrent users.
5. ~~How will we divide implementation work?~~ **Decided:** Sam focuses on frontend + MVP video gen. Jess focuses on infrastructure. Both do backend. Formal task assignment after backlog is created from this spec.
6. Terraform — who sets up the initial AWS infrastructure? Do we have an AWS account with sufficient permissions for ECS, ALB, ElastiCache, S3, DynamoDB, Lambda?
7. Cost controls — with many concurrent users, LLM costs multiply. Do we need per-session rate limits or a global budget cap?
8. ~~Data insights feedback loop~~ **Decided:** In scope. Manual data entry, feedback into prompts. See Section 2.4.
9. Which social media platforms will we post to? TikTok? YouTube Shorts? Instagram Reels? All three? (Affects the performance tracking form fields.)
10. What V1 hackathon code is reusable for the MVP? Need to audit `gemini-social-asset` to identify what carries over vs what needs rewriting.

---

## 13. Changelog

| Version | Date | Changes |
|---------|------|---------|
| v1.0 | 2026-03 | Jess's initial draft |
| v2.0 | 2026-03 | Sam's revision — 7-stage pipeline, multi-provider LLM, 3 experiments, detailed spec |
| v3.0 | 2026-03-23 | Multi-user + all-AWS revision. Railway → ECS Fargate. Added DynamoDB, Lambda, run isolation, cross-user caching, session model. Experiments updated for multi-tenant scenarios. Redis keys namespaced by run_id. |
| v3.1 | 2026-03-23 | Added S3 for file storage (DynamoDB stores metadata only, not files). Added performance feedback loop (Section 2.5) — manual data entry, metrics stored in DynamoDB, fed into pipeline prompts. Added two-track dev strategy (Section 2.6) — MVP on V1 code + distributed infra in parallel. Added /track and /insights pages. Added video_performance DynamoDB table. Added performance API endpoints. Updated AWS services to 8 (added S3, CloudWatch, IAM). |
| v3.2 | 2026-03-24 | Added content strategy section (Section 2.4) — structural patterns vs surface trends, platform anti-imitation mechanics, trend lifecycle analysis. Reframed feedback loop as pipeline calibration (not trend detection). Updated S1 to extract structural patterns only. Resolved OQ#2 — Kuaishou datasets are unsuitable, replaced with Tsinghua ShortVideo + TikTok-10M (see dataset-research.md). |

*This spec is the source of truth. Update it when architecture changes — don't let it drift from the code.*
