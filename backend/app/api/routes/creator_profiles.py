"""Sample creator profiles for the Create form's "Load example" dropdown.

Reads from backend/data/sample_creator_profiles.json at startup so new
profiles can be added without a code change.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.pipeline import CreatorProfile

router = APIRouter(tags=["creator-profiles"])

_SAMPLES_PATH = Path("data/sample_creator_profiles.json")


class SampleCreatorProfile(BaseModel):
    id: str
    label: str
    description: str
    profile: CreatorProfile


@router.get(
    "/api/creator-profiles/samples",
    response_model=list[SampleCreatorProfile],
)
async def list_sample_profiles() -> list[SampleCreatorProfile]:
    """Return the pre-authored creator profiles used to seed the form."""
    if not _SAMPLES_PATH.exists():
        raise HTTPException(
            status_code=500,
            detail=f"Sample profiles file not found at {_SAMPLES_PATH}",
        )
    data = json.loads(_SAMPLES_PATH.read_text())
    return [SampleCreatorProfile(**entry) for entry in data]
