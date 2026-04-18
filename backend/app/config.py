from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "flair2"
    debug: bool = False
    environment: str = "dev"

    # Redis (db=0 for state, db=1 for Celery broker — don't mix them)
    redis_url: str = "redis://localhost:6379/0"

    # CORS — comma-separated origins for production (e.g. "https://flair2.pages.dev")
    cors_origins: str = ""

    # AWS
    aws_region: str = "us-east-1"
    s3_bucket: str = "flair2-pipeline"
    dynamodb_runs_table: str = "pipeline_runs"
    dynamodb_perf_table: str = "video_performance"

    # LLM API Keys
    gemini_api_key: str = ""
    kimi_api_key: str = ""
    openai_api_key: str = ""

    # Rate Limits (requests per minute — retained for the backpressure experiment)
    gemini_rpm: int = 60
    kimi_rpm: int = 60
    openai_rpm: int = 60
    enable_rate_limiter: bool = True

    # Provider concurrency caps (in-flight requests). Kimi Code docs: 30. Leave
    # one headroom slot to avoid racing with the ceiling.
    kimi_max_concurrency: int = 29

    # Datasets (local paths — will be replaced by S3 in production)
    dataset_path: str = "data/sample_videos.json"
    personas_path: str = "data/personas.json"

    # Pipeline Defaults
    s1_video_count: int = 100
    s3_script_count: int = 20
    s4_persona_count: int = 42
    s6_top_n: int = 10

    # Completion thresholds — transition to next stage when this fraction
    # of fan-out tasks finished (completed or skipped). Prevents one
    # rate-limited straggler (~10min retry budget) from blocking the
    # whole run behind itself. Late completers still INCR counters; the
    # SETNX guard in the orchestrator ensures the transition fires once.
    s1_completion_threshold: float = 0.95
    s4_completion_threshold: float = 0.95

    # Celery (db=1 — separate from state Redis)
    celery_broker_url: str = "redis://localhost:6379/1"

    model_config = {"env_file": ".env", "env_prefix": "FLAIR2_"}


settings = Settings()
