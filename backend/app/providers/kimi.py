"""Kimi (Moonshot AI) reasoning provider via the Anthropic Messages API.

Kimi's coding endpoint migrated to an Anthropic-compatible schema
(see /coding/v1/messages). The legacy OpenAI /chat/completions shim
now returns a misleading "only 0.6 is allowed for this model" error
for every request, regardless of temperature — a dead surface.
"""

import asyncio
import json

import structlog
from pydantic import BaseModel, ValidationError

from app.config import settings
from app.models.errors import InvalidResponseError, ProviderError, RateLimitError
from app.providers.utils import extract_json

logger = structlog.get_logger()

BACKOFF_SECS = [1, 2, 4]
MAX_RETRIES = 3

# Anthropic SDK appends /v1/messages; base_url stops before that.
KIMI_BASE_URL = "https://api.kimi.com/coding"
KIMI_MODEL = "kimi-for-coding"
KIMI_USER_AGENT = "claude-code/0.1.0"
DEFAULT_MAX_TOKENS = 4096


class KimiProvider:
    name = "kimi"

    def __init__(self, api_key: str | None = None, model: str = KIMI_MODEL):
        self._api_key = api_key or settings.kimi_api_key
        self._model = model
        self._client = None
        self.last_usage: dict[str, int] | None = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic

            self._client = AsyncAnthropic(
                api_key=self._api_key,
                base_url=KIMI_BASE_URL,
                default_headers={"User-Agent": KIMI_USER_AGENT},
                timeout=120.0,
            )
        return self._client

    async def generate_text(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> str:
        client = self._get_client()
        token_budget = max_tokens or DEFAULT_MAX_TOKENS
        kwargs: dict = {
            "model": self._model,
            "max_tokens": token_budget,
            "messages": [{"role": "user", "content": prompt}],
        }
        if temperature is not None:
            kwargs["temperature"] = temperature

        for attempt in range(MAX_RETRIES):
            try:
                response = await client.messages.create(**kwargs)
                text = _extract_text(response)

                if response.usage:
                    self.last_usage = {
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    }

                if schema:
                    json_str = extract_json(text)
                    # Validate BOTH parse and schema-match: the LLM sometimes
                    # returns parseable JSON with the wrong shape (e.g. S3's
                    # hook/body/payoff when asked for S1's hook_type/pacing).
                    # Retrying in-provider is cheaper than letting the stage
                    # raise StageError, which bypasses Celery's retry path.
                    try:
                        parsed = json.loads(json_str)
                        schema.model_validate(parsed)
                    except (json.JSONDecodeError, ValidationError) as e:
                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                "kimi_invalid_schema",
                                attempt=attempt,
                                schema=schema.__name__,
                                error=str(e)[:300],
                            )
                            continue
                        raise InvalidResponseError(
                            f"Failed to produce valid {schema.__name__} "
                            f"after {MAX_RETRIES} attempts: {str(e)[:200]}",
                            provider=self.name,
                            raw_response=text,
                        ) from e
                    return json_str
                return text

            except (InvalidResponseError, ProviderError, RateLimitError):
                raise
            except Exception as e:
                error_str = str(e)
                body = getattr(e, "body", None) or getattr(e, "response", None)
                status_code = getattr(e, "status_code", None)
                if "429" in error_str or "rate" in error_str.lower():
                    logger.warning(
                        "kimi_rate_limit",
                        attempt=attempt,
                        status=status_code,
                        body=str(body)[:500] if body else None,
                        message=error_str[:500],
                    )
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(BACKOFF_SECS[attempt])
                        continue
                    raise RateLimitError(
                        f"Rate limited after {MAX_RETRIES} retries: {error_str[:200]}",
                        provider=self.name,
                        retry_after=BACKOFF_SECS[-1] * 2,
                    ) from e
                raise ProviderError(
                    error_str,
                    provider=self.name,
                    status_code=status_code,
                ) from e

        raise ProviderError("Unexpected retry exhaustion", provider=self.name)

    async def analyze_content(self, content: str, prompt: str) -> str:
        full_prompt = f"{prompt}\n\nContent to analyze:\n{content}"
        return await self.generate_text(full_prompt)


def _extract_text(response) -> str:
    """Flatten Anthropic Message.content blocks into a single string.

    response.content is a list of content blocks; text blocks have a `text`
    attribute. Tool-use blocks and other types are ignored for now.
    """
    parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)
