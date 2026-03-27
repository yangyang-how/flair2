class PipelineError(Exception):
    """Base — all pipeline errors inherit this."""

    def __init__(
        self,
        message: str,
        run_id: str | None = None,
        stage: str | None = None,
        attempt: int | None = None,
    ):
        self.run_id = run_id
        self.stage = stage
        self.attempt = attempt
        super().__init__(message)


class ProviderError(PipelineError):
    """LLM/Video API failure — retryable."""

    def __init__(
        self,
        message: str,
        provider: str,
        status_code: int | None = None,
        **kwargs,
    ):
        self.provider = provider
        self.status_code = status_code
        super().__init__(message, **kwargs)


class RateLimitError(ProviderError):
    """Rate limit hit — backoff and retry."""

    def __init__(self, message: str, retry_after: float | None = None, **kwargs):
        self.retry_after = retry_after
        super().__init__(message, **kwargs)


class InvalidResponseError(ProviderError):
    """LLM returned unparseable output — retry with stricter prompt."""

    def __init__(self, message: str, raw_response: str, **kwargs):
        self.raw_response = raw_response
        super().__init__(message, **kwargs)


class StageError(PipelineError):
    """Pipeline logic failure — halt the stage."""

    pass


class InfraError(PipelineError):
    """Redis/S3/DynamoDB failure — alert and retry."""

    def __init__(self, message: str, service: str, **kwargs):
        self.service = service
        super().__init__(message, **kwargs)
