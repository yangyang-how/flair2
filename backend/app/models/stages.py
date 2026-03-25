from datetime import datetime

from pydantic import BaseModel

from app.models.pipeline import CreatorProfile


class VideoInput(BaseModel):
    video_id: str
    transcript: str | None = None
    description: str | None = None
    duration: float
    engagement: dict


class S1Pattern(BaseModel):
    video_id: str
    hook_type: str
    pacing: str
    emotional_arc: str
    pattern_interrupts: list[str]
    retention_mechanics: list[str]
    engagement_triggers: list[str]
    structure_notes: str


class PatternEntry(BaseModel):
    pattern_type: str
    frequency: int
    examples: list[str]
    avg_engagement: float


class S2PatternLibrary(BaseModel):
    patterns: list[PatternEntry]
    total_videos_analyzed: int


class CandidateScript(BaseModel):
    script_id: str
    pattern_used: str
    hook: str
    body: str
    payoff: str
    estimated_duration: float
    structural_notes: str


class PersonaVote(BaseModel):
    persona_id: str
    persona_description: str
    top_5_script_ids: list[str]
    reasoning: str


class RankedScript(BaseModel):
    script_id: str
    vote_count: int
    score: float
    rank: int


class S5Rankings(BaseModel):
    top_10: list[RankedScript]
    total_votes_cast: int


class FinalResult(BaseModel):
    script_id: str
    original_script: CandidateScript
    personalized_script: str
    video_prompt: str
    rank: int = 0
    vote_score: float = 0.0


class S6Output(BaseModel):
    run_id: str
    results: list[FinalResult]
    creator_profile: CreatorProfile
    completed_at: datetime
