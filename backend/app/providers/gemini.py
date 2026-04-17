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


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str = "gemini-2.5-flash"):
        self._api_key = api_key or settings.gemini_api_key
        self._model = model
        self._client = None
        self.last_usage: dict[str, int] | None = None

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    async def generate_text(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
        max_tokens: int | None = None,
    ) -> str:
        client = self._get_client()
        config = {"max_output_tokens": max_tokens} if max_tokens else None
        for attempt in range(MAX_RETRIES):
            try:
                response = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self._model,
                    contents=prompt,
                    config=config,
                )
                # Capture token usage
                if hasattr(response, "usage_metadata") and response.usage_metadata:
                    self.last_usage = {
                        "input_tokens": getattr(response.usage_metadata, "prompt_token_count", 0),
                        "output_tokens": getattr(
                            response.usage_metadata, "candidates_token_count", 0
                        ),
                    }

                text = response.text
                if schema:
                    json_str = extract_json(text)
                    try:
                        json.loads(json_str)
                    except json.JSONDecodeError as e:
                        if attempt < MAX_RETRIES - 1:
                            logger.warning(
                                "invalid_json_response",
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
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    if attempt < MAX_RETRIES - 1:
                        await asyncio.sleep(BACKOFF_SECS[attempt])
                        continue
                    raise RateLimitError(
                        f"Rate limited after {MAX_RETRIES} retries",
                        provider=self.name,
                        retry_after=BACKOFF_SECS[-1] * 2,
                    ) from e
                raise ProviderError(
                    str(e),
                    provider=self.name,
                    status_code=getattr(e, "status_code", None),
                ) from e
        raise ProviderError("Unexpected retry exhaustion", provider=self.name)

    async def analyze_content(self, content: str, prompt: str) -> str:
        full_prompt = f"{prompt}\n\nContent to analyze:\n{content}"
        return await self.generate_text(full_prompt)
