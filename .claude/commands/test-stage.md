---
description: Test a pipeline stage end-to-end with sample brand input
argument-hint: [stage-name: discovery|studio|evaluation]
---

Run the specified pipeline stage against test fixtures and validate results.

## Setup

!`ls tests/fixtures/ 2>/dev/null || echo "No test fixtures directory yet"`

## Run

If the stage is implemented:
1. Run unit tests for the stage: `pytest tests/ -k $ARGUMENTS -v`
2. Check that external API calls (Gemini, web search) are mocked in tests
3. Check that the stage produces typed output matching its Pydantic model
4. Check that errors are typed (not generic Exception)
5. Check that retry logic exists for Gemini API calls

If the stage is NOT implemented yet:
1. List what modules need to exist based on the architecture doc
2. List what test fixtures are needed (sample inputs and expected outputs)
3. Draft the Pydantic models for the stage's input and output

Report findings and any gaps.
