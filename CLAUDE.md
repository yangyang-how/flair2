# AI Campaign Studio V2 (flair2)

V2 of Flair — AI Campaign Studio. Multi-stage AI pipeline that generates social media marketing campaigns for brands. Evolves V1 hackathon prototype with engineering rigor: specs, tests, CI/CD, code review, distributed architecture. Two-person project (Sam & Jess). V1 repo: https://github.com/yangyang-how/gemini-social-asset

Architecture and design rationale: see `design/architecture.md`. Read it before implementing pipeline features.

## Tech Stack
- **Backend:** Python 3.11+, FastAPI, Redis, Celery (or similar task queue)
- **Frontend:** Astro + React islands (TypeScript), Framer Motion
- **AI:** Gemini API (google-genai, google-adk)
- **Testing:** pytest
- **Linting:** ruff
- **Deploy:** Railway (backend), Cloudflare Pages (frontend)
- **CI:** GitHub Actions

## Commands
- Backend run: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Backend test: `pytest`
- Backend lint: `ruff check .`
- Backend format: `ruff format .`
- Frontend dev: [Fill in after Astro setup]
- Frontend build: [Fill in after Astro setup]

## Directory Structure
[Fill in during spec phase]

## Code Conventions
- Follow root garage CLAUDE.md (spec-first, branch workflow, one fix one PR)
- Every PR requires code review between Sam and Jess
- Conventional commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- Type hints on all function signatures
- Structured logging (no print statements)
- Environment-based config (dev/staging/prod)
- Comprehension checkpoints from the learning plan are acceptance criteria
- README documents every architectural decision with rationale ("we used X because Y")

## Gotchas
- Don't carry V1 shortcuts forward — spec-first discipline is required
- V1 has .DS_Store and __pycache__ committed — .gitignore from day one
- V1's main.py is monolithic — V2 must have clean module boundaries
- Gemini image generation returns intermittent 500s — need retry logic with backoff
- Gemini Live API sessions timeout after ~10 min inactivity
- Python backend is non-negotiable — resume requirement for agentic engineering roles
