# Architecture — AI Campaign Studio V2

## Architecture Decisions

This is a two-service architecture designed for three audiences: the distributed systems course, a resume for agentic engineering roles, and actual usability during development.

### Frontend (Cloudflare Pages)
Astro + React islands. Astro handles the static shell — forms, layout, campaign display. React islands hydrate only where we need interactivity: the pipeline stage visualization (long-running animation while the backend processes) and the audience voting animation (100 simulated audience members voting with visual aggregation). This split keeps the bundle small and the deploy instant. Cloudflare Pages gives us auto-deploy on every GitHub merge with preview URLs on every PR — we can test visually within minutes of merging.

### Backend (Railway)
Python/FastAPI with Redis for shared state and Celery (or similar) for the task queue. This is where the distributed systems work lives. The pipeline stages (discovery, studio, evaluation) run as concurrent workers coordinated through the message queue. The MapReduce pattern is used for audience evaluation — multiple worker processes evaluate the generated campaign in parallel (map), then results are aggregated by voting (reduce). Railway auto-deploys from GitHub like Cloudflare does, so the merge → test cycle works for both services.

### Why This Split
Python backend is the industry standard for AI services — every agentic engineering role expects it. Cloudflare Pages frontend gives us the instant deploy workflow that makes development fast. The two-service architecture itself demonstrates distributed systems thinking: an edge frontend communicating with an API backend, with internal distribution (workers, queues, Redis) inside the backend. This is three layers of distribution visible in one project.

### Frontend ↔ Backend Communication
SSE (Server-Sent Events) for pipeline status updates. The frontend opens an SSE connection when a campaign generation starts, and the backend streams stage completion events. This is better than polling for the visualization — the animation updates in real-time as each pipeline stage completes. For the voting visualization, the backend streams individual vote events so the frontend can animate each one.

## Pipeline Stages
1. **Discovery:** Brand input → material analysis → grounded web search → live voice interview → Brand Brain synthesis
2. **Studio:** Brand analysis → campaign direction generation (text + images) → user selection → full campaign production
3. **Evaluation (V2-new):** Multi-worker audience evaluation with MapReduce voting/aggregation

## Distributed Systems Concepts to Demonstrate
- **MapReduce:** Multiple workers evaluate content concurrently (map), results aggregated by voting (reduce)
- **Message queues:** Pipeline stages coordinated through Celery/Redis task queue
- **Redis:** Shared state, caching, pub/sub for worker coordination
- **Load balancing:** Distribute evaluation work across worker processes
- **SSE streaming:** Real-time event streaming from backend to frontend
- **Two-service architecture:** Edge frontend + API backend as a distributed system

## V1 → V2 Changes
- Monolithic `main.py` → separated orchestration, integration, and worker modules
- In-memory state → Redis-backed state management
- Sequential pipeline → concurrent workers with MapReduce patterns
- Vanilla JS single-page → Astro + React islands with animations
- Google Cloud Run → Railway (backend) + Cloudflare Pages (frontend)
- No tests → pytest with unit + integration coverage
- No CI → GitHub Actions on every push

## V2 Gaps to Close
1. **Spec-First Discipline** — design doc before any code
2. **Testing & CI** — pytest on day one, every module has unit tests, 5+ integration tests
3. **CI/CD & Production Hygiene** — lint + test + build on push, reliable Dockerfile, structured logging
4. **Review Muscle** — every PR reviewed, review log maintained
