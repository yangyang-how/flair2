# 15. Kimi and the Anthropic Messages Migration

> Industry-standard APIs come and go. Between the hackathon prototype and today, Flair2 migrated its LLM client twice — first to OpenAI's chat/completions schema, then to Anthropic's Messages API. This article explains why both moves happened, what the current wiring looks like, and the transferable lesson about coding against an interface.

## Two migrations in one project

When the Kimi provider was first added, Kimi's coding endpoint exposed an OpenAI-compatible `chat/completions` route. That made integration cheap: use the OpenAI Python SDK, swap `base_url`, done. Many Chinese LLM providers did this to attract developers already using OpenAI's SDK.

Then Kimi's endpoint quietly changed. The OpenAI-shaped route started returning a misleading error — `"only 0.6 is allowed for this model"` — for every request regardless of temperature. The real surface moved to an Anthropic Messages API shape at `/coding/v1/messages`. So we migrated again, this time to the Anthropic Python SDK.

This sequence is now permanently documented in the provider file's docstring:

```python
"""Kimi (Moonshot AI) reasoning provider via the Anthropic Messages API.

Kimi's coding endpoint migrated to an Anthropic-compatible schema
(see /coding/v1/messages). The legacy OpenAI /chat/completions shim
now returns a misleading "only 0.6 is allowed for this model" error
for every request, regardless of temperature — a dead surface.
"""
```

**The transferable lesson:** LLM provider APIs are not stable contracts. Public pricing pages and "OpenAI compatible" claims can change month to month. Design your provider abstraction so migrations are one file's worth of work.

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

Three things changed from the OpenAI era:

### 1. Different SDK

`AsyncAnthropic` instead of `OpenAI`. Same pattern (base_url + default_headers), different package. The rest of the provider code — retry logic, rate-limit handling, JSON parsing — didn't change because it doesn't depend on the SDK.

### 2. Different endpoint shape

`base_url` stops at `/coding`, not `/coding/v1`, because the Anthropic SDK appends `/v1/messages` automatically. Getting this wrong silently breaks everything with a 404.

### 3. Different request/response shape

Requests use `client.messages.create(...)` with `messages=[...]` and `max_tokens` (required in Anthropic's API, optional in OpenAI's). Responses are `Message` objects with a `content` list of content blocks — each block has a `type` ("text", "tool_use", etc.) and a `text` attribute for text blocks.

Flair2 only cares about text, so it flattens the content blocks:

```python
def _extract_text(response) -> str:
    parts: list[str] = []
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            parts.append(text)
    return "".join(parts)
```

## The User-Agent whitelist (still required)

Kimi's coding endpoint is gated on User-Agent. Only approved coding agents (Kimi CLI, Claude Code, Roo Code, etc.) can use it. Unrecognized clients get 403: *"Kimi For Coding is currently only available for Coding Agents."*

The `default_headers={"User-Agent": "claude-code/0.1.0"}` line is the whitelist workaround. Same fragility it had during the OpenAI era — if Kimi tightens validation, the spoof breaks. Nothing about migrating to Anthropic's SDK fixed this; it's an endpoint policy, not an SDK behavior.

## The registry abstraction paid off twice

Because every stage calls `provider.generate_text(...)` through the `ReasoningProvider` Protocol ([Article 14](14-the-provider-abstraction.md)), **two SDK migrations didn't touch any stage code.** S1, S3, S4, S6 have no idea which SDK sits behind the provider. The only files that changed across migrations:

- `providers/kimi.py` — the SDK wrapper
- `pyproject.toml` — the dependency (anthropic instead of openai)
- Tests that specifically asserted OpenAI SDK behavior

Every other part of the codebase — orchestrator, workers, stages, frontend — was unaffected. This is the dividend of programming to an interface. When the interface is stable and the implementation changes, only the implementation file changes.

## Model IDs

The coding endpoint accepts multiple model aliases:

| Model ID | What it is |
|----------|-----------|
| `kimi-for-coding` | Default; routes to the current coding-optimized model |
| `kimi-for-coding/k2p5` | Coding-specific variant of K2.5 |
| `kimi-k2.5` | General-purpose K2.5 (accepted on coding endpoint since Kimi unified their credit pool in April 2026) |

The code uses `kimi-for-coding` as the default. All three currently work because Kimi unified billing across Kimi Code, Kimi Chat, Agent, and PPT — the coding endpoint will accept general models too.

## Retry & rate-limit behavior

Provider-level retries are covered in [Article 16](16-rate-limiting.md). Key detail: the provider separates retry budgets by error class. Transient parse/schema errors get a short 3-attempt budget (1s/2s/4s). Concurrency rate limits (429s) get their own patient 4-attempt budget (8s/20s/45s/90s with ±30% jitter). The two don't share a budget, so a rate-limited task doesn't exhaust its retries on fast backoffs before the limit clears.

## What you should take from this

1. **"X-compatible API" claims are promises with an expiration date.** OpenAI compatibility worked for Kimi until it didn't. Don't hardcode to the shape; hide it behind an interface.

2. **`base_url` + `default_headers` is a pattern, not an SDK feature.** Both OpenAI's and Anthropic's Python SDKs expose it. If you're using one, you can use the other. The migration was ~30 lines.

3. **Endpoint policies (UA whitelist) survive SDK migrations.** When you switch clients, carry forward the policy workarounds or you'll be debugging a 403 for an hour.

4. **Provider code is churn-heavy; stage code shouldn't be.** Two migrations, zero changes to S1-S6. The interface pays for itself in rewrite-avoidance.

5. **Document the history in the docstring.** The "legacy OpenAI shim returns a misleading error" comment in `kimi.py` is load-bearing. Six months from now, somebody will try the OpenAI route again and be confused — the comment tells them why not to.

---

***Next: [Rate Limiting a Shared Upstream](16-rate-limiting.md) — the retry-budget-per-error-class pattern that keeps Flair2 alive under Kimi's concurrency throttling.***
