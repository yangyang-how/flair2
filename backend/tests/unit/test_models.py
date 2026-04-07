from datetime import UTC, datetime

from app.models.errors import (
    InfraError,
    InvalidResponseError,
    PipelineError,
    ProviderError,
    RateLimitError,
    StageError,
)
from app.models.performance import VideoPerformance
from app.models.pipeline import CreatorProfile, PipelineConfig
from app.models.stages import (
    CandidateScript,
    FinalResult,
    PatternEntry,
    PersonaVote,
    RankedScript,
    S1Pattern,
    S2PatternLibrary,
    S5Rankings,
    S6Output,
    VideoInput,
)


def test_creator_profile_valid():
    """Minimal profile — original 4 fields only (backward compat)."""
    p = CreatorProfile(
        tone="casual",
        vocabulary=["vibe", "insane"],
        catchphrases=["let's go"],
        topics_to_avoid=["politics"],
    )
    assert p.tone == "casual"
    assert len(p.vocabulary) == 2
    # Expanded fields default to None/empty
    assert p.niche is None
    assert p.audience_description is None
    assert p.content_themes == []
    assert p.example_hooks == []
    assert p.recent_topics == []


def test_creator_profile_expanded():
    """Full profile with niche, audience, themes — round-trip validation."""
    p = CreatorProfile(
        tone="casual and energetic",
        vocabulary=["vibe", "insane"],
        catchphrases=["let's gooo"],
        topics_to_avoid=["politics"],
        niche="fitness",
        audience_description="college students 18-24",
        content_themes=["morning routines", "dorm workouts"],
        example_hooks=["POV: your roommate sees you working out at 6am"],
        recent_topics=["push-up variations"],
    )
    assert p.niche == "fitness"
    assert p.audience_description == "college students 18-24"
    assert len(p.content_themes) == 2
    assert len(p.example_hooks) == 1
    assert len(p.recent_topics) == 1

    # Round-trip through JSON
    data = p.model_dump()
    p2 = CreatorProfile(**data)
    assert p2.niche == "fitness"
    assert p2.content_themes == ["morning routines", "dorm workouts"]


def test_pipeline_config_valid():
    c = PipelineConfig(
        run_id="test-run-1",
        session_id="session-1",
        reasoning_model="gemini",
        video_model=None,
        creator_profile=CreatorProfile(
            tone="edgy", vocabulary=[], catchphrases=[], topics_to_avoid=[]
        ),
    )
    assert c.reasoning_model == "gemini"
    assert c.video_model is None


def test_video_input_valid():
    v = VideoInput(
        video_id="vid_001",
        transcript="Hey what's up, today we're going to...",
        description="How to go viral #fyp",
        duration=15.0,
        engagement={"views": 1000000, "likes": 50000},
    )
    assert v.duration == 15.0


def test_s1_pattern_valid():
    p = S1Pattern(
        video_id="vid_001",
        hook_type="question",
        pacing="fast_slow_fast",
        emotional_arc="curiosity_gap",
        pattern_interrupts=["visual cut at 3s"],
        retention_mechanics=["open loop"],
        engagement_triggers=["relatability"],
        structure_notes="Opens with a direct question, slow reveal, payoff at end",
    )
    assert p.hook_type == "question"


def test_s2_pattern_library():
    lib = S2PatternLibrary(
        patterns=[
            PatternEntry(
                pattern_type="question_hook",
                frequency=25,
                examples=["vid_001", "vid_015"],
                avg_engagement=85000.0,
            ),
        ],
        total_videos_analyzed=100,
    )
    assert lib.total_videos_analyzed == 100
    assert lib.patterns[0].frequency == 25


def test_candidate_script():
    s = CandidateScript(
        script_id="script_001",
        pattern_used="question_hook + fast_slow_fast",
        hook="Have you ever wondered why some videos get millions of views?",
        body="The secret is in the first 3 seconds...",
        payoff="Try this on your next video and watch what happens.",
        estimated_duration=30.0,
        structural_notes="Question hook, curiosity gap, practical payoff",
    )
    assert s.estimated_duration == 30.0


def test_persona_vote():
    v = PersonaVote(
        persona_id="persona_0",
        persona_description="18-year-old college student, watches comedy and lifestyle content",
        top_5_script_ids=["script_001", "script_015", "script_030", "script_042", "script_007"],
        reasoning="Script 001 had the strongest hook...",
    )
    assert len(v.top_5_script_ids) == 5


def test_s5_rankings():
    r = S5Rankings(
        top_10=[
            RankedScript(script_id="script_001", vote_count=45, score=0.92, rank=1),
            RankedScript(script_id="script_015", vote_count=38, score=0.85, rank=2),
        ],
        total_votes_cast=100,
    )
    assert r.top_10[0].rank == 1


def test_final_result():
    script = CandidateScript(
        script_id="script_001",
        pattern_used="question",
        hook="hook",
        body="body",
        payoff="payoff",
        estimated_duration=25.0,
        structural_notes="notes",
    )
    fr = FinalResult(
        script_id="script_001",
        original_script=script,
        personalized_script="Yo what's up...",
        video_prompt="A fast-paced montage...",
        rank=1,
        vote_score=0.92,
    )
    assert fr.personalized_script.startswith("Yo")


def test_s6_output():
    output = S6Output(
        run_id="run-1",
        results=[],
        creator_profile=CreatorProfile(
            tone="casual", vocabulary=[], catchphrases=[], topics_to_avoid=[]
        ),
        completed_at=datetime.now(UTC),
    )
    assert output.run_id == "run-1"


def test_video_performance():
    vp = VideoPerformance(
        run_id="run-1",
        script_id="script_001",
        platform="tiktok",
        post_url="https://tiktok.com/@user/video/123",
        posted_at=datetime.now(UTC),
        views=50000,
        likes=3000,
        comments=150,
        shares=500,
        watch_time_avg=12.5,
        completion_rate=65.0,
        committee_rank=1,
        script_pattern="question_hook",
    )
    assert vp.platform == "tiktok"


def test_error_hierarchy():
    base = PipelineError("something broke", run_id="run-1", stage="S1", attempt=2)
    assert base.run_id == "run-1"
    assert base.stage == "S1"
    assert isinstance(base, Exception)

    provider = ProviderError("API down", provider="gemini", status_code=500, run_id="run-1")
    assert isinstance(provider, PipelineError)
    assert provider.provider == "gemini"

    rate = RateLimitError("too fast", provider="gemini", retry_after=30.0)
    assert isinstance(rate, ProviderError)

    invalid = InvalidResponseError("bad json", provider="gemini", raw_response="{broken")
    assert isinstance(invalid, ProviderError)

    stage = StageError("logic error", run_id="run-1", stage="S3")
    assert isinstance(stage, PipelineError)

    infra = InfraError("connection lost", service="redis")
    assert isinstance(infra, PipelineError)
    assert infra.service == "redis"
