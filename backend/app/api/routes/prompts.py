"""Prompt-template preview endpoint.

Returns the raw template strings used by each LLM stage so the frontend
can show users, live, how their Creator Profile fields flow into the
actual prompt. Templates use Python str.format() placeholders
(`{field}`); the frontend substitutes those on the client side.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from app.pipeline.prompts.s1_prompts import S1_ANALYZE_PROMPT
from app.pipeline.prompts.s3_prompts import S3_FEEDBACK_SECTION, S3_GENERATE_PROMPT
from app.pipeline.prompts.s4_prompts import S4_FEEDBACK_SECTION, S4_VOTE_PROMPT
from app.pipeline.prompts.s6_prompts import S6_PERSONALIZE_PROMPT

router = APIRouter(tags=["prompts"])


class PromptTemplates(BaseModel):
    s1: str
    s3: str
    s3_feedback: str
    s4: str
    s4_feedback: str
    s6: str


@router.get("/api/prompts/preview", response_model=PromptTemplates)
async def get_prompt_templates() -> PromptTemplates:
    """Return raw prompt templates for the four LLM-using stages.

    Frontend renders these with Creator Profile fields substituted so
    users see exactly what the LLM will see.
    """
    return PromptTemplates(
        s1=S1_ANALYZE_PROMPT,
        s3=S3_GENERATE_PROMPT,
        s3_feedback=S3_FEEDBACK_SECTION,
        s4=S4_VOTE_PROMPT,
        s4_feedback=S4_FEEDBACK_SECTION,
        s6=S6_PERSONALIZE_PROMPT,
    )
