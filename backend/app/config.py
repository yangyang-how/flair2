from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "flair2"
    debug: bool = False
    environment: str = "dev"

    # LLM API Keys
    gemini_api_key: str = ""
    kimi_api_key: str = ""
    openai_api_key: str = ""

    # Pipeline Defaults
    s1_video_count: int = 100
    s3_script_count: int = 50
    s4_persona_count: int = 100
    s6_top_n: int = 10

    model_config = {"env_file": ".env", "env_prefix": "FLAIR2_"}


settings = Settings()
