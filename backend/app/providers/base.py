from typing import Protocol

from pydantic import BaseModel


class ReasoningProvider(Protocol):
    """Any LLM that generates text."""

    name: str

    async def generate_text(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str: ...

    async def analyze_content(
        self,
        content: str,
        prompt: str,
    ) -> str: ...


class VideoJobStatus(BaseModel):
    job_id: str
    status: str
    video_url: str | None = None
    error: str | None = None


class VideoProvider(Protocol):
    """Any service that generates video clips."""

    name: str

    async def generate_video(
        self,
        prompt: str,
        duration: int = 6,
    ) -> bytes: ...

    async def check_status(
        self,
        job_id: str,
    ) -> VideoJobStatus: ...
