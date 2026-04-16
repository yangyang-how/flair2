"""Kimi (Moonshot AI) reasoning provider via OpenAI-compatible API."""

import asyncio
import json

import structlog
from pydantic import BaseModel

from app.config import settings
from app.models.errors import InvalidResponseError, ProviderError, RateLimitError
from app.providers.utils import extract_json

logger = structlog.get_logger()

BACKOFF_SECS = [1, 2, 4]
MAX_RETRIES = 3

KIMI_BASE_URL = "https://api.kimi.com/coding/v1"
KIMI_MODEL = "kimi-k2.5"
KIMI_USER_AGENT = "claude-code/0.1.0"


class KimiProvider:
    name = "kimi"

    def __init__(self, api_key: str | None = None, model: str = KIMI_MODEL):
        self._api_key = api_key or settings.kimi_api_key
        self._model = model
        self._client = None
        self.last_usage: dict[str, int] | None = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(
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
    ) -> str:
        client = self._get_client()
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.to_thread(
                    client.chat.completions.create,
                    model=self._model,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=32768,
                )
                text = response.choices[0].message.content

                if response.usage:
                    self.last_usage = {
                        "input_tokens": response.usage.prompt_tokens,
                        "output_tokens": response.usage.completion_tokens,
                    }

                if schema:
                    json_str = extract_json(text)
                    try:
                        json.loads(json_str)
                    except json.JSONDecodeError as e:
                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                "kimi_invalid_json",
                                attempt=attempt,
                                error=str(e),
                            )
                            continue
                        raise InvalidResponseError(
                            f"Failed to parse JSON after {MAX_RETRIES} attempts",
                            provider=self.name,
                            raw_response=text,
                        ) from e
                    return json_str
                return text

            except (InvalidResponseError, ProviderError, RateLimitError):
                raise
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate" in error_str.lower():
                    if attempt < MAX_RETRIES - 1:
                        logger.warning(
                            "kimi_rate_limit",
                            attempt=attempt,
                            backoff=BACKOFF_SECS[attempt],
                        )
                        await asyncio.sleep(BACKOFF_SECS[attempt])
                        continue
                    raise RateLimitError(
                        f"Rate limited after {MAX_RETRIES} retries",
                        provider=self.name,
                        retry_after=BACKOFF_SECS[-1] * 2,
                    ) from e
                raise ProviderError(
                    error_str,
                    provider=self.name,
                    status_code=getattr(e, "status_code", None),
                ) from e

        raise ProviderError("Unexpected retry exhaustion", provider=self.name)

    async def analyze_content(self, content: str, prompt: str) -> str:
        full_prompt = f"{prompt}\n\nContent to analyze:\n{content}"
        return await self.generate_text(full_prompt)
