# Project Spec — Pattern Learning & Crowd-Validated Content Generation for Short-Form Video

| | |
|---|---|
| **Authors** | Sam Wu · Jess |
| **Course** | CS6650 — Distributed Systems |
| **Version** | v2.0 — March 2026 (updated from Jess's v1.0 draft) |
| **Status** | Draft — under review |
| **Repo** | https://github.com/yangyang-how/flair2 |

---

## 1. Problem

Creators who want to make viral short-form videos currently do so by manually watching hundreds of top-performing videos, trying to intuit patterns, and then writing scripts by hand. This process is slow, subjective, and produces scripts that sound like copies rather than authentic content.

This system automates the pattern-extraction phase and the generation phase, while using a crowd-simulation voting step to surface the highest-potential content before personalizing it to the creator's own voice.

**Three output modes** — the system produces, for each top-ranked script:
1. **Video scripts** — personalized to creator's voice, for humans to shoot themselves
2. **Video prompts** — structured prompts ready for any AI video generator
3. **Generated videos** — 4–8 second AI-generated clips, on-demand per script (user picks which ones to generate — not all 10)

**The academic goal** is to implement two full MapReduce cycles on AWS-compatible infrastructure (Railway + Redis), observe distributed systems phenomena (backpressure, partial failure recovery, cache concurrency), and produce measurable experimental results.

**The resume goal** is a portfolio piece demonstrating: distributed AI pipeline architecture, configurable multi-provider LLM integration, crowd-simulation evaluation, and a polished web frontend with real-time pipeline visualization.

---

## 2. Architecture

### 2.1 Two-Service Architecture

| Service | Stack | Deploy | Purpose |
|---------|-------|--------|---------|
| **Frontend** | Astro + React islands (TypeScript), Framer Motion | Cloudflare Pages | Input forms, pipeline visualization, voting animation, output display |
| **Backend** | Python 3.11+, FastAPI, Redis, Celery | Railway | AI pipeline, worker coordination, LLM provider routing |

**Why this split:** Python backend is the industry standard for AI services (resume signal). Cloudflare Pages gives instant deploy with preview URLs on every PR (development speed). The two-service architecture itself demonstrates distributed systems thinking for the course.

**Communication:** SSE (Server-Sent Events) for real-time pipeline status. The frontend opens an SSE connection when generation starts; the backend streams stage completion events and individual vote events for the voting animation.

### 2.2 Pipeline Overview

Six stages, two MapReduce cycles, one sequential generation step, one style-injection step.

```
INPUT: 100 videos from Tsinghua/Kuaishou dataset

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

S7 VIDEO GENERATION (on-demand, user-triggered)
   user selects 1-3 scripts  →  generate 4-8s video clip per selection

OUTPUT:
  - 10 personalized scripts with viral structure + authentic voice
  - 10 video prompts ready for AI generation
  - 1-3 generated video clips (only for scripts the user explicitly chose)
```

### 2.3 Module Responsibilities

| **Stage** | Responsibility | Provider Group |
|-----------|---------------|---------------|
| **S1 Analyze (Map)** | Call LLM once per video. Extract: hook type, pacing, structure, engagement triggers. Output: JSON pattern object per video. | Reasoning |
| **S2 Aggregate (Reduce)** | Merge N pattern objects into a deduplicated pattern library. Output: ranked pattern list with frequency counts. | Algorithmic (no LLM) |
| **S3 Generate** | Sequential. For each top pattern, generate a script variant. 50 scripts total. No parallelism — deliberate bottleneck for Amdahl's Law observation. | Reasoning |
| **S4 Vote (Map)** | Simulate 100 viewer personas, each evaluating all 50 candidate **scripts** (text only — not prompts or videos) and predicting their top 5 picks. One LLM call per persona-worker. | Reasoning |
| **S5 Rank (Reduce)** | Aggregate votes into a ranked leaderboard. Output: top 10 scripts by vote score. | Algorithmic (no LLM) |
| **S6 Personalize + Prompt** | For each of top 10: (a) rewrite script to match creator voice, (b) generate structured video prompt. All text — no video generation here. | Reasoning |
| **S7 Generate Video (on-demand)** | User selects 1-3 scripts from the results page and explicitly triggers video generation. One 4-8s clip per selected script. This is NOT part of the automated pipeline — it's a separate user-initiated action. | Video |
| **Redis** | Shared state for all workers. Task queue (BRPOP/RPUSH), result storage, token bucket rate limiter, SETNX cache lock. | — |
| **Orchestrator** | Starts workers, monitors stage completion, streams SSE events to frontend, handles timeouts. | — |

### 2.4 LLM Provider Architecture

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
Handles: generating 4-8 second video clips (S6c) only.

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

All providers implement the appropriate interface. The orchestrator reads the user's selection from the pipeline request, not from a static config file. This means different runs can use different providers without restarting the backend.

---

## 3. Frontend

### 3.1 Pages

| Page | What It Shows |
|------|-------------|
| **/** | Landing — project description, start button |
| **/create** | Input form: upload creator_profile.json or fill in fields (tone, vocabulary, catchphrases, topics_to_avoid). Model selection: Reasoning model dropdown (Kimi 2.5 / Gemini / GPT-4o-mini) + Video model dropdown (Seedance 2.0 / Google Veo / Skip video). Start pipeline button. |
| **/pipeline** | Real-time pipeline visualization. Six stages shown as connected nodes. Each stage animates as it processes (progress bar, item count). SSE-powered. |
| **/vote** | Voting visualization. 100 simulated audience members appear as avatars. Each evaluates the 50 candidate **scripts** and casts votes in real-time (animated). Votes aggregate into a leaderboard showing the top 10 scripts. This is the visual centerpiece. |
| **/results** | Final output display. Tab view: Scripts / Video Prompts. Each of the top 10 results shown with the creator's personalized version alongside the original. Each script has a "Generate Video" button — user picks 1-3 to generate, video appears when ready (async, may take 1-3 minutes). |

### 3.2 Interactive Components (React Islands)

Only three components need React hydration — the rest is static Astro:

1. **PipelineVisualizer** — SSE-connected, shows stage progress in real-time, Framer Motion transitions between stages
2. **VotingAnimation** — 100 avatar grid, each avatar animates when casting a vote, leaderboard updates live, Framer Motion for vote movements
3. **VideoPlayer** — Plays generated 4-8s clips on the results page. Shows loading state while video generates (1-3 min). Only appears for scripts where user clicked "Generate Video."

---

## 4. Data Flow

| **Input** | Tsinghua/Kuaishou 10K user preference dataset. Use first 100 videos by engagement rank. |
|---|---|
| **S1 → S2** | Redis list: `pattern:{video_id}` keys, each a JSON blob with hook, pacing, structure fields. |
| **S2 → S3** | Redis key: `pattern_library`, a JSON array sorted by frequency. |
| **S3 → S4** | Redis list: `scripts:candidates`, 50 JSON script objects. |
| **S4 → S5** | Redis list: `votes:{persona_id}`, each a list of 5 script IDs. SSE events streamed to frontend per vote. |
| **S5 → S6** | Redis key: `top_scripts`, array of top 10 script IDs + scores. |
| **S6 → Output** | Redis key: `results:final`, array of 10 objects, each containing: personalized script + video prompt. |
| **S7 (on-demand)** | User triggers via `/api/video/generate`. Result stored at `results:video:{script_id}`, containing video URL. Frontend polls until ready. |
| **Creator Voice** | Input via web form or file upload: `creator_profile.json`. Fields: tone, vocabulary, catchphrases, topics_to_avoid. |

---

## 5. API Contracts

### 5.1 LLM Provider Usage

| **Reasoning model** | User-selected per run (Kimi 2.5, Gemini, or GPT-4o-mini) |
|---|---|
| **Video model** | User-selected per run (Seedance 2.0, Google Veo, or skip) |
| **Rate limit** | Token bucket in Redis per provider — configurable per API's actual limits |
| **S1 prompt output** | JSON: `{ hook_type, pacing, structure, engagement_triggers[] }` |
| **S4 prompt output** | JSON: `{ top_5_script_ids: [id, id, id, id, id] }` |
| **S6a output** | String: rewritten script text |
| **S6b output** | JSON: structured video prompt |
| **S6c output** | Binary: video file (mp4, 4-8s) |
| **Total reasoning calls (est.)** | ~260 (100 analyze + 50 generate + 100 vote + 10 personalize/prompt) |
| **Total video calls (est.)** | 1-3 per run (user-triggered, on demand) |

### 5.2 Redis Key Schema

```
task:s1              LIST   — video IDs pending S1 analysis (BRPOP queue)
result:s1:{video_id} STRING — JSON pattern object from S1
pattern_library      STRING — JSON array, written by S2
task:s4              LIST   — persona IDs pending S4 voting (BRPOP queue)
result:s4:{persona}  STRING — JSON list of 5 script IDs
top_scripts          STRING — JSON array of top 10 {id, score}
results:final        STRING — JSON array of 10 {script, prompt}
results:video:{id}   STRING — JSON {status, video_url} — written by S7 on demand
cache:{key}          STRING — SETNX-protected shared computation cache
ratelimit:{provider} STRING — Token bucket counter per provider (expires per window)
checkpoint:{stage}   STRING — Last completed task index for recovery
sse:events           LIST   — SSE event queue for frontend streaming
```

### 5.3 Backend API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/pipeline/start` | POST | Start pipeline with creator profile + model selections (`{ creator_profile, reasoning_model, video_model }`) |
| `/api/pipeline/status` | GET (SSE) | Stream pipeline events to frontend |
| `/api/pipeline/results` | GET | Get final results (10 scripts + prompts) after completion |
| `/api/video/generate` | POST | User-triggered: generate video for a specific script (`{ script_id }`) |
| `/api/video/status/{job_id}` | GET | Poll video generation status (processing / complete / failed) |
| `/api/providers` | GET | List available reasoning and video providers (for frontend dropdowns) |
| `/api/health` | GET | Health check |

---

## 6. Failure Modes & Handling

| **Failure** | Handling Strategy |
|---|---|
| **LLM rate limit hit (any provider)** | Token bucket limiter in Redis prevents proactively. If still received: exponential backoff with jitter, max 3 retries. |
| **Worker crash mid-stage** | Checkpoint written to Redis after each task. On restart, worker reads `checkpoint:{stage}` and resumes from last completed index. |
| **LLM returns invalid JSON** | JSON parse with try/except. On failure: retry once with stricter prompt. On second failure: skip item, log error, continue pipeline. |
| **Redis connection lost** | Workers retry connection with backoff. If Redis down > 30s: pipeline halts, SSE error event sent to frontend. |
| **S3 bottleneck timeout** | S3 is sequential by design. If exceeds 10 min: reduce to top 20 patterns, log truncation. |
| **Video generation timeout** | Seedance/Veo may take 60-180s per clip. Use async polling with webhook. If timeout > 5 min: skip video, deliver script + prompt only. |
| **Video generation fails** | Fallback to alternate provider. If both fail: deliver script + prompt without video. Log which provider failed and why. |
| **LLM API down (any provider)** | Try fallback provider. If all providers down: fail fast after 3 consecutive failures, save checkpoint, send error to frontend. |
| **Empty dataset** | Validate input at startup. If < 10 videos: halt with descriptive error before any API calls. |
| **Frontend loses SSE connection** | Auto-reconnect with exponential backoff. Frontend shows "reconnecting..." state. On reconnect, fetch current stage from `/api/pipeline/status`. |

---

## 7. Experiments

### Experiment 1 — Backpressure Under Load

| **Concept** | Flow control — token bucket rate limiting |
|---|---|
| **Problem** | N workers share one LLM API with rate limits. Without control, workers flood the endpoint, triggering rate limit cascades. |
| **Setup** | Run S1 with N = 1, 5, 10, 20, 50 workers. Two conditions per N: (a) no rate limiter, (b) Redis token bucket limiter. |
| **Measure** | Requests/min actually sent, error rate, total stage completion time. |
| **Expected** | No limiter: error rate spikes sharply past N=10. With limiter: throughput plateaus gracefully near the API limit, near-zero errors. |
| **Success criterion** | Limiter condition produces < 1% error rate at N=50. No-limiter condition produces measurable error rate at N > 10. |

### Experiment 2 — Partial Failure Recovery

| **Concept** | Fault tolerance — checkpoint-based recovery |
|---|---|
| **Problem** | Worker crash at task 37 of 100 means 36 completed tasks are wasted without checkpointing. |
| **Setup** | Kill a worker at 25%, 50%, and 75% completion. Compare: (a) full restart, (b) checkpoint resume, (c) graceful degradation using partial results. |
| **Measure** | Recovery time, redundant API calls, output quality correlation with full run. |
| **Expected** | Checkpoint recovery is O(1) regardless of crash point. Partial results at > 50% completion are > 90% correlated with full run. |
| **Success criterion** | Checkpoint resume saves > 40% of API calls vs full restart in all three crash scenarios. |

### Experiment 3 — Cache Concurrency Safety

| **Concept** | Atomicity — SETNX vs naive GET/SET |
|---|---|
| **Problem** | 50 workers may compute the same cached value simultaneously, causing duplicate LLM calls and data inconsistency. |
| **Setup** | 50 workers sharing a script summary cache. Condition A: naive GET then SET. Condition B: atomic SETNX. |
| **Measure** | Duplicate LLM calls per cache key, total API cost, consistency of cached values. |
| **Expected** | SETNX: exactly one computation per key. Naive: duplicate calls proportional to concurrency. |
| **Success criterion** | SETNX produces exactly 1 LLM call per cache key across 50 concurrent workers. |

---

## 8. Success Criteria

- Given 100 input videos, S1 produces exactly 100 pattern objects with no missing fields.
- S2 produces a non-empty pattern library with at least 3 distinct pattern types.
- S3 produces exactly 50 candidate scripts without halting.
- S4 produces votes from exactly 100 simulated personas, with SSE events visible in the frontend voting animation.
- S5 produces a ranked top-10 list with scores attached.
- S6 produces 10 final results, each containing: personalized script + video prompt.
- Video generation (S7) successfully produces a clip when user triggers it for a selected script.
- Full pipeline (S1–S6) completes in under 60 minutes with 10 workers. Video generation (S7) is separate and on-demand.
- All three experiments produce data sufficient for a results table.
- Pipeline survives a simulated worker crash without manual intervention.
- Frontend displays real-time pipeline progress and voting animation.
- LLM provider can be selected from the web UI per run without restarting the backend.

---

## 9. Non-Goals

- No real TikTok/Kuaishou API integration — data comes from the research dataset only.
- No persistent database — Redis is ephemeral state, output goes to API responses and local files.
- No multi-user support — single creator profile per run.
- No production deployment optimizations (auto-scaling, CDN for videos) — this is a course project.
- Not optimizing content quality — the goal is distributed systems behavior + configurable AI pipeline architecture.
- Not polishing the script → prompt → video quality funnel. Each transition (text to prompt, prompt to video) introduces quality decay. Optimizing prompt templates and evaluating video fidelity against script intent is V3 scope — V2 proves the pipeline works end-to-end.
- No user authentication — the frontend is open.

---

## 10. Tech Stack

| **Backend language** | Python 3.11+ |
|---|---|
| **Frontend language** | TypeScript (Astro + React) |
| **Reasoning LLM** | Kimi 2.5, Google Gemini, OpenAI GPT-4o-mini — user-selectable per run |
| **Video generation** | Seedance 2.0 via PiAPI, Google Veo — user-selectable per run, or skip |
| **Coordination** | Redis 7 (task queues, checkpoints, rate limiter, cache, SSE events) |
| **Task queue** | Celery (or similar, backed by Redis) |
| **Backend framework** | FastAPI |
| **Frontend framework** | Astro + React islands, Framer Motion |
| **Backend deploy** | Railway (GitHub auto-deploy, preview environments) |
| **Frontend deploy** | Cloudflare Pages (GitHub auto-deploy, preview URLs per PR) |
| **Testing** | pytest (backend), [frontend testing TBD] |
| **Linting** | ruff (backend) |
| **CI** | GitHub Actions — lint + test on every push |
| **Dataset** | Tsinghua/Kuaishou 10K user preference dataset |

---

## 11. Open Questions

*Resolve these before writing code:*

1. How will we structure the `creator_profile.json`? What fields are required vs. optional? (The web form needs to match.)
2. What does the Kuaishou dataset actually contain per record? Do we need to preprocess it before S1?
3. Kimi 2.5 rate limits — what are they? Confirm before Experiment 1 setup.
4. Seedance 2.0 API pricing via PiAPI — what's the cost per 4-8s clip? Budget for 1-3 clips per run (user-triggered, not batch).
5. Will we use Railway's managed Redis or a separate Redis provider (Upstash)?
6. How will we divide implementation work between Sam and Jess? Suggested split: Sam owns S1–S3 + Redis infra + frontend, Jess owns S4–S6 + experiments harness + LLM provider interface.
7. Does the course require AWS specifically, or is Railway acceptable? If AWS required, adjust backend deploy.

*This spec is the source of truth. Update it when architecture changes — don't let it drift from the code.*
