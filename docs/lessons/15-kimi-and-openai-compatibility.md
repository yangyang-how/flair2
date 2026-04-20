# 15. Kimi and the Anthropic Messages API

> Kimi (Moonshot AI) is Flair2's production LLM. Its coding endpoint speaks the Anthropic Messages API shape, gated on a User-Agent allowlist. This article walks through how the provider is wired, why each knob is set the way it is, and the transferable lessons about coding against an API you don't own.

## The endpoint, the SDK, and the UA allowlist

Kimi exposes several surfaces. The one Flair2 uses is **Kimi For Coding** at `https://api.kimi.com/coding`. That endpoint speaks the **Anthropic Messages API** at `/coding/v1/messages` — same request shape, same response shape, same content-block structure as calling Claude directly. Because the shape matches, Flair2 reaches it with the standard `anthropic` Python SDK (`AsyncAnthropic`) and just overrides `base_url`.

Two non-obvious things about that endpoint:

1. **It's gated on User-Agent.** Only approved coding agents (Claude Code, Kimi CLI, Roo Code, Cline, etc.) are allowed through. Unknown clients get a 403 with the message *"Kimi For Coding is currently only available for Coding Agents."* We set `default_headers={"User-Agent": "claude-code/0.1.0"}` to land on the allowlist.
2. **The base URL stops at `/coding`, not `/coding/v1`.** The Anthropic SDK appends `/v1/messages` itself. Adding `/v1` to the base URL yields a silent 404.

The docstring on the provider file calls this out for anyone reading the code cold:

```python
"""Kimi (Moonshot AI) reasoning provider via the Anthropic Messages API.

Kimi's coding endpoint uses an Anthropic-compatible schema
(see /coding/v1/messages). Requires a coding-agent User-Agent
on the allowlist, or the endpoint returns 403.
"""
```

## The current wiring

**File:** `backend/app/providers/kimi.py`

```python
KIMI_BASE_URL = "https://api.kimi.com/coding"  # no /v1 — SDK appends /v1/messages
KIMI_MODEL = "kimi-for-coding"                 # or "kimi-k2.5"
KIMI_USER_AGENT = "claude-code/0.1.0"

class KimiProvider:
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
```

Three details worth understanding in that block:

### 1. `AsyncAnthropic`, lazily constructed

The SDK client is created on first use, not on import. That means importing `providers/kimi.py` is free — no network, no auth validation, no side effects. You pay the cost only when a task actually calls the provider. This matters for tests and for cold-start latency on worker tasks.

### 2. `base_url` stops at `/coding`

The Anthropic SDK appends `/v1/messages` automatically. If you write `base_url="https://api.kimi.com/coding/v1"`, the final URL becomes `/coding/v1/v1/messages` and you get a silent 404 for every request. Read the SDK's URL-composition rules before setting `base_url`.

### 3. Content-block responses, not plain strings

`client.messages.create(...)` returns a `Message` object with a `content` list. Each block has a `type` (`"text"`, `"tool_use"`, etc.) and a `text` attribute for text blocks. Flair2 only cares about text, so it flattens the blocks:

```python
def _extract_text(response) -> str:
    parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)
```

## The User-Agent allowlist

The UA header is the other piece of this that trips up newcomers. The endpoint returns 403 for anything it doesn't recognize, and nothing in the Anthropic SDK forces you to set a UA — so if you follow the SDK's quickstart with Kimi's `base_url`, every request fails and the error message ("Kimi For Coding is currently only available for Coding Agents") points you in an unhelpful direction.

`default_headers={"User-Agent": "claude-code/0.1.0"}` solves it. The value has to match an entry on Kimi's internal allowlist. It's an endpoint policy, not an SDK behavior, so it survives any SDK change — keep it in mind any time you touch this file.

## Why the abstraction isolates this

All of the above — the SDK choice, the `base_url` quirk, the UA header, the content-block flattening — lives entirely inside `providers/kimi.py`. Stages S1, S3, S4, S6 don't know any of it. They call `provider.generate_text(...)` through the `ReasoningProvider` Protocol ([Article 14](14-the-provider-abstraction.md)) and get a plain string back.

That's the dividend of programming to an interface. If Kimi's endpoint tightens its UA policy, if the content-block response shape evolves, if a future provider uses a different SDK — the change lives in one file. The rest of the codebase doesn't notice.

## Model IDs

The coding endpoint accepts multiple model aliases:

| Model ID | What it is |
|----------|-----------|
| `kimi-for-coding` | Default; routes to the current coding-optimized model |
| `kimi-for-coding/k2p5` | Coding-specific variant of K2.5 |
| `kimi-k2.5` | General-purpose K2.5 (accepted on coding endpoint since Kimi unified their credit pool in April 2026) |

The code uses `kimi-for-coding` as the default. All three currently work because Kimi unified billing across Kimi Code, Kimi Chat, Agent, and PPT, so the coding endpoint accepts general models too.

## Retry & rate-limit behavior

Provider-level retries are covered in [Article 16](16-rate-limiting.md). Key detail: the provider separates retry budgets by error class. Transient parse/schema errors get a short 3-attempt budget (1s/2s/4s). Concurrency rate limits (429s) get their own patient 4-attempt budget (8s/20s/45s/90s with ±30% jitter). The two don't share a budget, so a rate-limited task doesn't exhaust its retries on fast backoffs before the limit clears.

## What you should take from this

1. **`base_url` + `default_headers` is how you bend a vendor SDK to a non-default endpoint.** Both OpenAI's and Anthropic's Python SDKs expose these. You don't need a custom HTTP client to target a compatible endpoint; the existing SDK already does everything.

2. **Read the SDK's URL-composition rules before setting `base_url`.** The Anthropic SDK appends `/v1/messages` itself. Getting this wrong is silent — you get a 404 with no useful diagnostic.

3. **Endpoint policies (like UA allowlists) live outside SDK abstractions.** No amount of Protocol + Registry purity saves you from a 403. Document the policy workaround in the provider file so future readers don't spend an hour debugging auth.

4. **Content-block responses are the Anthropic SDK's native shape, not a Kimi quirk.** If you ever call Claude directly, the same flattening logic applies.

5. **Lazy client construction keeps imports side-effect-free.** `_get_client()` is called on first use, not at module load. Your tests and cold starts thank you.

---

***Next: [Rate Limiting a Shared Upstream](16-rate-limiting.md) — the retry-budget-per-error-class pattern that keeps Flair2 alive under Kimi's concurrency throttling.***
