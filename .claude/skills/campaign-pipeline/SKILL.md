---
name: campaign-pipeline
description: >
  Flair2 AI campaign generation pipeline architecture. Use when working on
  pipeline stages (discovery, studio, evaluation), Celery task design,
  MapReduce evaluation, Redis state management, SSE streaming, or Gemini
  API integration. Also use when discussing distributed systems patterns
  in the context of this project.
allowed-tools: Read, Grep, Glob
---

# Flair2 Campaign Pipeline

Reference: `design/architecture.md`

## Pipeline Overview

Three-stage AI pipeline that generates social media marketing campaigns:

```
Brand Input → Discovery → Studio → Evaluation → Campaign Output
```

All stages run as Celery tasks coordinated through Redis.

## Stage 1: Discovery

Brand input → material analysis → grounded web search → live voice interview → Brand Brain synthesis.

- Input: brand name, URL, uploaded materials
- Output: Brand Brain document (structured brand analysis)
- AI: Gemini for analysis and synthesis, web search for grounding
- Model tier: capable (Gemini Pro / equivalent)

## Stage 2: Studio

Brand Brain → campaign direction generation (text + images) → user selection → full campaign production.

- Input: Brand Brain from Discovery
- Output: multiple campaign directions, then full production of selected direction
- AI: Gemini for text + image generation
- Model tier: capable for direction generation, standard for production
- User interaction: user selects preferred direction mid-pipeline

## Stage 3: Evaluation (V2-new, MapReduce)

Generated campaign → multi-worker audience evaluation → aggregated scoring.

- Input: completed campaign from Studio
- Output: audience scores, feedback, vote breakdown
- Pattern: MapReduce
  - Map: N worker processes each simulate an audience persona evaluating the campaign
  - Reduce: aggregate votes, compute scores, surface common feedback themes
- AI: cheap model (Gemini Flash / equivalent) per worker — many parallel calls
- Redis pub/sub for worker coordination and result collection

## Distributed Systems Patterns

| Pattern | Where Used | Purpose |
|---------|-----------|---------|
| Task queue (Celery) | All stages | Async pipeline execution, retry, monitoring |
| MapReduce | Evaluation | Parallel audience simulation + vote aggregation |
| Pub/Sub (Redis) | Evaluation + SSE | Worker coordination + real-time frontend updates |
| SSE streaming | Frontend ← Backend | Real-time pipeline progress + vote animation |
| Shared state (Redis) | All stages | Campaign state, intermediate results, session data |

## Key Constraints

- Gemini image generation returns intermittent 500s — every AI call needs retry with exponential backoff
- Gemini Live API sessions timeout after ~10 min inactivity — implement keepalive or reconnect
- Pipeline stages communicate through the task queue, never direct function calls
- All AI calls go through a provider interface — never import SDK directly from pipeline code
- Each stage's input/output is a Pydantic model — typed contracts between stages

## Two-Service Architecture

- **Backend** (Railway): Python/FastAPI + Redis + Celery workers
- **Frontend** (Cloudflare Pages): Astro + React islands
- Communication: REST for actions, SSE for real-time updates
- Both auto-deploy from GitHub on merge to main
