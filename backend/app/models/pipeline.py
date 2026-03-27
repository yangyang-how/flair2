from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class CreatorProfile(BaseModel):
    tone: str
    vocabulary: list[str]
    catchphrases: list[str]
    topics_to_avoid: list[str]


class PipelineConfig(BaseModel):
    run_id: str
    session_id: str
    reasoning_model: str
    video_model: str | None = None
    creator_profile: CreatorProfile


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineRun(BaseModel):
    run_id: str
    session_id: str
    status: PipelineStatus
    config: PipelineConfig
    current_stage: str | None = None
    stages: dict[str, StageStatus] = {}
    created_at: datetime
    completed_at: datetime | None = None
    s3_results_key: str | None = None
    error: str | None = None
