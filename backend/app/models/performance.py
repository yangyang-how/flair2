from datetime import datetime

from pydantic import BaseModel


class VideoPerformance(BaseModel):
    run_id: str
    script_id: str
    platform: str
    post_url: str
    posted_at: datetime
    views: int
    likes: int
    comments: int
    shares: int
    watch_time_avg: float | None = None
    completion_rate: float | None = None
    committee_rank: int
    script_pattern: str
