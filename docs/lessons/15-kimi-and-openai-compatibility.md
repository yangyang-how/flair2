# 15. Kimi and the OpenAI Compatibility Layer

> Most new LLM providers ship an OpenAI-compatible API endpoint. Understanding why this pattern exists and how it works gives you a practical skill: swap LLM providers without rewriting client code.

## The industry pattern

OpenAI's Chat Completions API has become a de facto standard. The key endpoint:

```
POST /v1/chat/completions
{
  "model": "gpt-4",
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 1000
}
```

Many LLM providers — including Kimi (Moonshot AI), Together AI, Groq, Anyscale, Fireworks, and dozens of others — implement this exact API shape at their own endpoint. You can use the official OpenAI Python SDK, point it at a different `base_url`, and it works.

**Why providers do this:** the OpenAI SDK is the most widely used LLM client library. By matching its API, providers get instant compatibility with every tool, framework, and tutorial that uses the OpenAI SDK. It's free adoption.

**Why this matters for you:** if you build your LLM integration around the OpenAI SDK, switching providers is a configuration change (new base URL + API key), not a code rewrite.

## How Kimi uses it

**File:** `backend/app/providers/kimi.py`

```python
KIMI_BASE_URL = "https://api.kimi.com/coding/v1"
KIMI_MODEL = "kimi-for-coding/k2p5"
KIMI_USER_AGENT = "claude-code/0.1.0"

class KimiProvider:
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
```

Three things are swapped from the default OpenAI configuration:

### 1. `base_url`

Instead of `https://api.openai.com/v1`, requests go to `https://api.kimi.com/coding/v1`. The SDK appends the endpoint path (`/chat/completions`) to this base URL. All request/response formatting stays the same.

### 2. `api_key`

Kimi has its own API keys, separate from OpenAI. The key is passed to the same `api_key` parameter. The SDK includes it as a `Bearer` token in the `Authorization` header, which is the standard OAuth2 pattern.

### 3. `default_headers`

```python
default_headers={"User-Agent": KIMI_USER_AGENT}
```

This is the interesting one. Kimi requires (or at least expects) a specific User-Agent header. The OpenAI SDK's default User-Agent is something like `openai-python/1.x.x`. Kimi might reject or rate-limit requests with that UA.

The `default_headers` parameter on the OpenAI client adds these headers to every request. This is the workaround for provider-specific quirks that the standard API shape doesn't account for.

**PR history:** this was fixed in PR #67 ("fix: use OpenAI default_headers for Kimi User-Agent"). Before that, the UA was being set some other way that didn't work reliably.

## The API call

```python
response = await asyncio.to_thread(
    client.chat.completions.create,
    model=self._model,
    messages=[{"role": "user", "content": prompt}],
    max_tokens=32768,
)
text = response.choices[0].message.content
```

**`asyncio.to_thread`:** the OpenAI Python SDK's synchronous client (`OpenAI`, not `AsyncOpenAI`) is used here, wrapped in `asyncio.to_thread` to avoid blocking the event loop. This runs the synchronous HTTP call in a thread pool.

**Why not `AsyncOpenAI`?** It would work too. The choice of sync-in-thread vs async is a pragmatic one — both work, sync is simpler to debug (stack traces are clearer), and the threading overhead is negligible for 2-5 second LLM calls.

**Response parsing:** `response.choices[0].message.content` — the standard OpenAI response structure. Kimi returns responses in the same format: a list of `choices`, each with a `message` containing `role` and `content`.

**Token usage:**
```python
if response.usage:
    self.last_usage = {
        "input_tokens": response.usage.prompt_tokens,
        "output_tokens": response.usage.completion_tokens,
    }
```

The `usage` field is part of the OpenAI response spec. Kimi populates it. This lets Flair2 track token consumption across calls — useful for cost monitoring.

## Comparing with GeminiProvider

Gemini does NOT use the OpenAI-compatible pattern. It has its own SDK:

```python
# Gemini — different SDK, different API:
from google import genai
client = genai.Client(api_key=self._api_key)
response = await asyncio.to_thread(
    client.models.generate_content,
    model=self._model,
    contents=prompt,
)
text = response.text
```

Different import, different client class, different method name, different response structure. This is why the `ReasoningProvider` abstraction exists — it hides these differences behind a common `generate_text()` method.

If Gemini offered an OpenAI-compatible endpoint (some Google models do through Vertex AI), both providers could use the same OpenAI SDK with different base URLs. The abstraction would still be useful (different rate limit detection, different error shapes), but the client code would be nearly identical.

## The `extract_json` utility

**File:** `backend/app/providers/utils.py`

Both providers use a shared utility to extract JSON from LLM responses. LLMs often wrap JSON in markdown code fences:

````
Here is the analysis:

```json
{"hook_type": "question", "pacing": "fast", ...}
```

I hope this helps!
````

`extract_json()` strips the wrapping and returns just the JSON string. This is a shared concern — all LLM providers have this problem, regardless of which API they use.

## Retry and error handling

Both KimiProvider and GeminiProvider implement the same retry pattern:

```python
BACKOFF_SECS = [1, 2, 4]
MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    try:
        response = ...  # API call
        # parse response...
        return result
    except Exception as e:
        if is_rate_limit(e):
            await asyncio.sleep(BACKOFF_SECS[attempt])
            continue
        raise ProviderError(str(e), provider=self.name)
```

**Exponential backoff:** 1s, 2s, 4s. Each retry waits longer. This is the standard pattern for handling rate limits — give the provider time to reset its counter.

**Rate limit detection is provider-specific:**
- Kimi: `"429" in str(e) or "rate" in str(e).lower()`
- Gemini: `"429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)`

The error string matching is fragile (it depends on the exact error message format), but it works for known providers. A more robust approach would check `e.status_code == 429` directly.

## Adding a new provider

To add a hypothetical Claude provider:

1. Create `backend/app/providers/claude.py`:
```python
class ClaudeProvider:
    name = "claude"
    async def generate_text(self, prompt, schema=None):
        # Use Anthropic SDK
        ...
```

2. Register it in `backend/app/providers/registry.py`:
```python
from app.providers.claude import ClaudeProvider
_reasoning_providers["claude"] = ClaudeProvider
```

3. Add `claude_api_key` and `claude_rpm` to `backend/app/config.py`

4. Add `"claude": settings.claude_api_key` to `_get_provider`'s `key_map` in `tasks.py`

That's it. No stage functions change. No orchestrator changes. No SSE changes. No tests change (except adding provider-specific tests).

## What you should take from this

1. **OpenAI-compatible APIs are the industry standard.** If you're integrating with an LLM provider, check if they have an OpenAI-compatible endpoint. If they do, you can reuse the OpenAI SDK.

2. **`base_url` + `api_key` + `default_headers` are the three knobs.** That's all you need to point the OpenAI SDK at a different provider.

3. **`asyncio.to_thread` is the bridge between sync and async.** When you have a synchronous SDK and an async application, wrap the call in `to_thread` to avoid blocking the event loop.

4. **Shared utilities (`extract_json`) reduce code duplication across providers.** Provider-specific code handles auth and error detection; shared code handles response parsing.

5. **Every provider will need custom error detection.** HTTP 429 is standard, but the error message format varies. Encapsulate provider-specific error handling inside the provider class, not in the caller.

---

***Next: [Rate Limiting a Shared Upstream](16-rate-limiting.md) — the token bucket algorithm, centralized vs distributed rate limiting, and a documented race condition.***
