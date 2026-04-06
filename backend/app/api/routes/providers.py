"""Provider listing endpoint."""

from fastapi import APIRouter

from app.providers.registry import list_providers

router = APIRouter(tags=["providers"])


@router.get("/api/providers")
async def get_providers() -> dict:
    """List available reasoning and video providers for frontend dropdowns."""
    return list_providers()
