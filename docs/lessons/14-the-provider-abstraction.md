# 14. The Provider Abstraction

> Flair2 switched its entire LLM backend from Gemini to Kimi in one PR. The reason it was possible is a 30-line abstraction layer that most developers would dismiss as "premature." This article explains why it wasn't, and teaches you the design pattern behind it.

## The payoff story

PR #95: "chore: remove Gemini secret requirement, Kimi-only deployment."

Here's what changed: the Terraform config stopped provisioning a Gemini API key, and the default reasoning model in the frontend was set to "kimi." That's it. No stage functions were modified. No task definitions changed. No tests broke (except the ones specifically testing GeminiProvider).

The switch was possible because no code in the pipeline says `KimiProvider` or `GeminiProvider`. It says `ReasoningProvider`. The specific implementation is chosen at runtime, from configuration.

**Cost of the abstraction:** ~30 lines of code (the Protocol class + the registry). **Payoff:** hours of migration work avoided, plus the ability to switch providers again in the future without touching business logic.

## The Protocol class

**File:** `backend/app/providers/base.py`

```python
class ReasoningProvider(Protocol):
    name: str

    async def generate_text(
        self,
        prompt: str,
        schema: type[BaseModel] | None = None,
    ) -> str: ...

    async def analyze_content(
        self,
        content: str,
        prompt: str,
    ) -> str: ...
```

**`Protocol` is Python's structural typing.** Unlike abstract base classes (which require inheritance), a Protocol defines an interface through structure. Any class that has a `name: str`, a `generate_text` method with the right signature, and an `analyze_content` method with the right signature is automatically a `ReasoningProvider` — without inheriting from anything.

This is **duck typing made explicit:** "if it walks like a provider and quacks like a provider, it IS a provider."

**Why Protocol over ABC:**

```python
# Abstract Base Class approach (inheritance required):
class ReasoningProvider(ABC):
    @abstractmethod
    async def generate_text(self, prompt: str, ...) -> str: ...

class KimiProvider(ReasoningProvider):  # MUST inherit
    async def generate_text(self, prompt: str, ...) -> str: ...

# Protocol approach (structural, no inheritance):
class ReasoningProvider(Protocol):
    async def generate_text(self, prompt: str, ...) -> str: ...

class KimiProvider:  # No inheritance needed
    async def generate_text(self, prompt: str, ...) -> str: ...
```

**With Protocol:** `KimiProvider` doesn't even know `ReasoningProvider` exists. It just has the right methods. This is looser coupling — the provider implementation doesn't depend on the abstraction. In practice, Flair2's providers don't inherit from `ReasoningProvider` and don't import it.

## The Registry

**File:** `backend/app/providers/registry.py`

```python
from app.providers.gemini import GeminiProvider
from app.providers.kimi import KimiProvider

_reasoning_providers: dict[str, type] = {
    "gemini": GeminiProvider,
    "kimi": KimiProvider,
}

def get_reasoning_provider(name: str, **kwargs):
    if name not in _reasoning_providers:
        raise ValueError(
            f"Unknown reasoning provider: {name}. Available: {list(_reasoning_providers)}"
        )
    return _reasoning_providers[name](**kwargs)

def list_providers() -> dict:
    return {
        "reasoning": list(_reasoning_providers.keys()),
        "video": list(_video_providers.keys()),
    }
```

**The registry pattern:** a dictionary mapping string names to classes. `get_reasoning_provider("kimi", api_key="...")` looks up `KimiProvider` in the dict and instantiates it.

**Why a registry, not an if/else chain?**

```python
# Without registry (don't do this):
def get_provider(name, **kwargs):
    if name == "kimi":
        return KimiProvider(**kwargs)
    elif name == "gemini":
        return GeminiProvider(**kwargs)
    elif name == "openai":
        return OpenAIProvider(**kwargs)
    else:
        raise ValueError(f"Unknown: {name}")

# With registry:
_providers = {"kimi": KimiProvider, "gemini": GeminiProvider}
def get_provider(name, **kwargs):
    return _providers[name](**kwargs)
```

The registry version is better because:
1. **Adding a provider is one line** (add to dict) vs modifying a function
2. **`list_providers()` is free** — just return the dict keys
3. **The registry is data, not logic** — you can modify it at runtime (e.g., `register_reasoning("claude", ClaudeProvider)`)
4. **No risk of forgetting to update the if/else** when adding a new provider

**This is the Strategy pattern + Factory pattern combined.** Strategy: different implementations behind a common interface. Factory: the registry creates the right implementation from a string name.

## How the provider is selected at runtime

**File:** `backend/app/workers/tasks.py`

```python
def _get_provider(config: PipelineConfig):
    key_map = {
        "gemini": settings.gemini_api_key,
        "kimi": settings.kimi_api_key,
        "openai": settings.openai_api_key,
    }
    return get_reasoning_provider(
        config.reasoning_model,
        api_key=key_map.get(config.reasoning_model, "")
    )
```

The pipeline config carries `reasoning_model: str` (e.g., `"kimi"`). The task wrapper looks up the API key from settings and passes both to the registry.

**The user chooses the provider.** The `StartPipelineRequest` includes `reasoning_model: str`. Different pipeline runs can use different providers. The infrastructure is provider-agnostic; the choice is per-request.

## The two provider implementations

### KimiProvider (`providers/kimi.py`)

```python
class KimiProvider:
    name = "kimi"

    def __init__(self, api_key=None, model=KIMI_MODEL):
        self._api_key = api_key or settings.kimi_api_key
        self._model = model
        self._client = None

    def _get_client(self):
        if self._client is None:
            from anthropic import AsyncAnthropic
            self._client = AsyncAnthropic(
                api_key=self._api_key,
                base_url=KIMI_BASE_URL,                        # "https://api.kimi.com/coding"
                default_headers={"User-Agent": KIMI_USER_AGENT},
                timeout=120.0,
            )
        return self._client
```

Kimi speaks the **Anthropic Messages API** on its coding endpoint. We use the `AsyncAnthropic` client with a custom `base_url`. (An earlier version of Kimi spoke OpenAI's chat/completions schema instead — that surface went dead and the client had to migrate. [Article 15](15-kimi-and-openai-compatibility.md) covers the migration history and why the abstraction let us do it with a ~30-line change.)

### GeminiProvider (`providers/gemini.py`)

```python
class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key=None, model="gemini-2.5-flash"):
        self._api_key = api_key or settings.gemini_api_key
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(api_key=self._api_key)
        return self._client
```

Gemini uses the official Google `genai` SDK. Different SDK, different call pattern — but the `generate_text` method presents the same interface to callers.

### What's the same

Both providers:
- Have a `name` attribute
- Lazily initialize their client (`_get_client()`)
- Implement retry logic with exponential backoff (3 attempts, 1s/2s/4s delays)
- Detect rate limits from error messages/status codes
- Parse JSON from LLM responses and validate
- Track token usage in `last_usage`
- Raise typed errors (`ProviderError`, `RateLimitError`, `InvalidResponseError`)

### What's different

| Aspect | KimiProvider | GeminiProvider |
|--------|-------------|----------------|
| SDK | OpenAI Python SDK | Google genai SDK |
| Auth | API key + custom headers | API key |
| JSON extraction | `extract_json(text)` | `extract_json(text)` |
| Rate limit detection | `"429" in str(e)` | `"429" or "RESOURCE_EXHAUSTED"` |
| Default model | `kimi-for-coding/k2p5` | `gemini-2.5-flash` |

**The helper `extract_json()`** (in `providers/utils.py`) strips markdown code fences and other wrapping from LLM responses to extract the actual JSON. Both providers need this because LLMs often wrap JSON in ````json\n...\n```` blocks.

## The `VideoProvider` Protocol

```python
class VideoProvider(Protocol):
    name: str
    async def generate_video(self, prompt: str, duration: int = 6) -> bytes: ...
    async def check_status(self, job_id: str) -> VideoJobStatus: ...
```

A second Protocol for video generation. Currently has no implementations — the video generation pipeline (Lambda-based, using Seedance or Veo) was planned but never built. The Protocol exists as a contract for future work.

The registry already has a `_video_providers` dict and a `register_video` function. Adding a video provider would follow the exact same pattern as the reasoning providers.

## When abstraction is premature vs prescient

The common objection: "You only have two providers. This is premature abstraction. Just use Kimi directly."

Here's why it wasn't premature:

1. **The switch actually happened.** Gemini → Kimi migration was driven by Gemini's intermittent 500s and rate limit issues. Without the abstraction, every stage function would have needed modification.

2. **The cost was trivial.** Protocol class: 15 lines. Registry: 20 lines. Zero runtime overhead. The abstraction doesn't add complexity to the codebase — it removes it from every stage function.

3. **The interface was obvious.** All LLM providers do the same thing: take a prompt, return text. The interface didn't require speculation — it was dictated by the domain.

**When abstraction IS premature:** when you're guessing at the interface. If you don't know what the methods should look like, an abstraction will be wrong. Wait until you have two concrete implementations and extract the commonality.

**Rule of thumb:** abstract when (a) the interface is obvious from the domain, (b) you have at least one concrete implementation, and (c) the cost of the abstraction is small relative to the cost of changing callers later.

## What you should take from this

1. **Protocol > ABC for provider interfaces.** Structural typing means implementations don't need to import or inherit from the interface. Looser coupling, fewer imports, same type safety.

2. **The Registry pattern is a Strategy + Factory hybrid.** Dictionary mapping names to classes. Adding a provider is one line. Listing providers is one function call.

3. **Abstraction pays for itself when the switch actually happens.** The Gemini → Kimi migration is the proof. Without the abstraction, it would have been a week of find-and-replace across stage functions, tests, and error handling.

4. **The interface should be dictated by the domain, not the implementation.** All LLM providers take prompts and return text. That's the interface. Implementation details (SDK choice, auth mechanism, retry strategy) are hidden behind it.

5. **Lazy initialization with `_get_client()` avoids import-time side effects.** The SDK is imported and the client is created only when the first call happens. This means importing the module doesn't trigger network connections or API validation.

---

***Next: [Kimi and OpenAI Compatibility](15-kimi-and-openai-compatibility.md) — what "OpenAI-compatible" means as an industry pattern.***
