"""HTTP-level request/response models.

Contract: https://github.com/yangyang-how/flair2/issues/71 Section 3.
"""

from pydantic import BaseModel

from app.models.pipeline import CreatorProfile

# ── Pipeline ────────────────────────────────────────────────


class StartPipelineRequest(BaseModel):
    creator_profile: CreatorProfile
    reasoning_model: str  # "kimi" | "gemini" | "openai"
    video_model: str | None = None  # "seedance" | "veo" | None
    num_videos: int = 100  # S1 video count
    num_scripts: int = 20  # S3 script count
    num_personas: int = 42  # S4 persona count
    top_n: int = 10  # S5/S6 top N scripts


class StartPipelineResponse(BaseModel):
    run_id: str


class RunStatusResponse(BaseModel):
    run_id: str
    status: str  # "pending" | "running" | "completed" | "failed"
    current_stage: str | None
    stages: dict[str, str]  # stage_name → status


class RunListResponse(BaseModel):
    runs: list[RunStatusResponse]


# ── Video ───────────────────────────────────────────────────


class GenerateVideoRequest(BaseModel):
    run_id: str
    script_id: str


class GenerateVideoResponse(BaseModel):
    job_id: str


class VideoStatusResponse(BaseModel):
    job_id: str
    status: str  # "processing" | "complete" | "failed"
    video_url: str | None = None
    error: str | None = None


# ── Performance ─────────────────────────────────────────────


class SubmitPerformanceRequest(BaseModel):
    run_id: str
    script_id: str
    platform: str
    post_url: str
    views: int
    likes: int
    comments: int
    shares: int
    watch_time_avg: float | None = None
    completion_rate: float | None = None


# ── SSE ─────────────────────────────────────────────────────


class SSEEvent(BaseModel):
    id: str  # Redis Stream message ID
    event: str
    data: dict
    timestamp: str
