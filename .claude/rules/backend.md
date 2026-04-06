---
paths:
  - "backend/**"
  - "app/**"
---
# Backend Rules (Python / FastAPI)

## Architecture
- Each pipeline stage (discovery, studio, evaluation) is a separate module.
- Celery tasks are thin wrappers — business logic lives in service modules, not task definitions.
- All Gemini API calls go through a provider interface — never import google-genai directly from pipeline logic.
- Redis access goes through a client abstraction — no raw redis calls scattered across modules.
- Pipeline stages communicate through the task queue, not direct function calls.

## Testing
- Every module has a test file in tests/ mirroring the source structure.
- Mock all external API calls (Gemini, web search) in unit tests.
- Integration tests use real Redis but mocked AI APIs.
- Test fixtures go in tests/fixtures/ — real brand inputs with expected outputs.

## Type Safety
- Type hints on every function signature — no exceptions.
- Use Pydantic models for all API request/response schemas and inter-stage data.
- Use enums for pipeline stages and status values, not string literals.

## Error Handling
- Pipeline errors are typed (DiscoveryError, StudioError, EvaluationError) — never raise generic Exception.
- A failed stage should report clearly and not silently continue to the next stage.
- Gemini API errors get retried with exponential backoff for transient failures (500s, timeouts).
- Log every error with structured context (stage, brand_id, attempt_number).

## Code Style
- ruff for linting and formatting — run before every commit.
- Conventional commits: feat:, fix:, refactor:, docs:, test:, chore:
- No print statements — use structured logging.
- Config from environment variables via pydantic-settings, never hardcoded.
