# 13. The Six Stage Functions

> Each pipeline stage is a pure function: input in, output out, no side effects. This article walks through all six, explains the patterns they share, and shows why purity matters for testing, debugging, and reuse.

## What "pure function" means here

A pure function:
1. Takes explicit inputs (no reading from global state, databases, or files)
2. Returns an output
3. Has no side effects (no writing to databases, no sending messages)
4. Given the same inputs, produces the same output (mostly — LLMs add nondeterminism)

Flair2's stage functions are pure in the first three senses. They take a provider and input data, return structured output, and don't touch Redis, Celery, or the SSE stream. The Celery task wrapper handles all infrastructure concerns.

**Why this matters:** pure functions are testable without infrastructure. You can test `s1_analyze` by passing a mock provider — no Redis, no Celery, no network. The stage function doesn't know or care that it's running inside a distributed pipeline.

## The shared pattern: prompt → call → parse → validate

Every LLM-calling stage (S1, S3, S4, S6) follows the same structure:

```python
async def stage_function(input_data, provider: ReasoningProvider) -> OutputModel:
    # 1. Build the prompt from a template
    prompt = PROMPT_TEMPLATE.format(field1=input_data.field1, ...)

    # 2. Call the LLM
    response = await provider.generate_text(prompt, schema=OutputModel)

    # 3. Parse the JSON response
    data = json.loads(response)

    # 4. Validate and return
    return OutputModel(**data)
```

**Step 1 — Prompt building:** each stage has a prompt template in `pipeline/prompts/`. Templates use Python string formatting (`{field_name}`) to inject data. This keeps the prompt logic separate from the stage logic.

**Step 2 — LLM call:** `provider.generate_text(prompt, schema=OutputModel)` sends the prompt and receives text. The `schema` parameter hints to the provider that structured JSON output is expected (though the current implementation doesn't use JSON mode — it relies on the prompt to request JSON).

**Step 3 — JSON parsing:** the LLM returns a string that should contain JSON. `json.loads()` parses it. If parsing fails, `InvalidResponseError` is raised (the provider retries this internally up to 3 times).

**Step 4 — Pydantic validation:** the parsed dict is fed to a Pydantic model constructor, which validates types and required fields. If the LLM omitted a field or returned the wrong type, Pydantic raises a validation error.

## S1: Analyze (`s1_analyze.py`)

**Input:** one `VideoInput` (video_id, transcript, description, duration, engagement metrics)
**Output:** one `S1Pattern` (hook_type, pacing, emotional_arc, pattern_interrupts, retention_mechanics, engagement_triggers, structure_notes)
**LLM calls:** 1

```python
async def s1_analyze(video: VideoInput, provider: ReasoningProvider) -> S1Pattern:
    prompt = S1_ANALYZE_PROMPT.format(
        video_id=video.video_id,
        duration=video.duration,
        description=video.description or "(no description)",
        transcript=video.transcript or "(no transcript)",
        engagement=json.dumps(video.engagement),
    )
    response = await provider.generate_text(prompt, schema=S1Pattern)
    data = json.loads(response)
    data["video_id"] = video.video_id  # Override — LLM may hallucinate a different ID
    return S1Pattern(**data)
```

**Notable detail:** `data["video_id"] = video.video_id` overrides whatever the LLM returned. LLMs sometimes hallucinate field values, especially identifiers. Hardcoding the known-correct value is a defensive pattern — trust your own data, not the LLM's echo of it.

**Error handling hierarchy:** `json.JSONDecodeError` → `InvalidResponseError` (parser failure). Other exceptions → `StageError` (generic stage failure). The task wrapper catches both and reports to the orchestrator.

## S2: Aggregate (`s2_aggregate.py`)

**Input:** list of `S1Pattern` (all S1 results for this run)
**Output:** one `S2PatternLibrary`
**LLM calls:** 0

```python
def s2_aggregate(patterns: list[S1Pattern]) -> S2PatternLibrary:
    groups: dict[str, list[S1Pattern]] = defaultdict(list)
    for p in patterns:
        key = f"{p.hook_type} + {p.pacing}"
        groups[key].append(p)

    entries = []
    for key, group in groups.items():
        entries.append(PatternEntry(
            pattern_type=key,
            frequency=len(group),
            examples=[p.video_id for p in group[:5]],
            avg_engagement=0.0,
        ))

    entries.sort(key=lambda e: e.frequency, reverse=True)
    return S2PatternLibrary(patterns=entries, total_videos_analyzed=len(patterns))
```

**Not async, not an LLM call.** This is pure Python — `defaultdict`, list comprehensions, sorting. It groups patterns by their combined `hook_type + pacing` key, counts how often each combination appears, and sorts by frequency.

**Design choice:** S2 is deliberately algorithmic. You could ask an LLM to "synthesize these 100 patterns into a unified library," but: (a) it would be nondeterministic, (b) it would cost tokens, (c) the aggregation logic is simple enough that code is better than AI. **Use AI for creativity; use code for math.**

**The `avg_engagement=0.0` placeholder:** engagement averaging isn't implemented. The field exists in the model for future use. This is pragmatic — define the data shape now, fill in the value later. Better than retroactively adding a field to a model that's already in production.

## S3: Generate (`s3_generate.py`)

**Input:** `S2PatternLibrary` + optional `VideoPerformance` feedback
**Output:** list of `CandidateScript`
**LLM calls:** up to `num_scripts` (default 50)

S3 is the most complex stage. Key points:

**Proportional distribution:** scripts are allocated across patterns proportional to frequency. If "question hook + fast pacing" appeared in 30 of 100 videos, it gets ~30% of the 50 scripts.

```python
for pattern in library.patterns:
    count = max(1, round(target * pattern.frequency / total_freq))
```

**UUID-based script IDs:** `data["script_id"] = str(uuid.uuid4())[:8]`. Each script gets a short UUID. This is generated on our side, not by the LLM, because we need stable identifiers for voting and ranking.

**Feedback loop:** if `VideoPerformance` data exists from previous runs, it's included in the prompt. This is the mechanism for the pipeline to improve over time — past performance data influences future script generation.

**Error tolerance:** if a single script generation fails (LLM error), the function logs a warning and continues. Only if ALL scripts fail does it raise `StageError`. This is **graceful degradation** — partial failure doesn't kill the entire stage.

```python
except Exception as e:
    logger.warning("s3_script_failed", error=str(e), pattern=pattern.pattern_type)
    continue
```

**Strict count enforcement:** after the loop, if fewer than `target` scripts were generated, `StageError` is raised. The pipeline needs exactly `num_scripts` candidates for S4 voting — fewer would produce statistically weak rankings.

## S4: Vote (`s4_vote.py`)

**Input:** list of `CandidateScript` + persona_id
**Output:** one `PersonaVote` (persona_id, persona_description, top_5_script_ids, reasoning)
**LLM calls:** 1

```python
async def s4_vote(scripts, persona_id, provider, feedback=None):
    prompt = S4_VOTE_PROMPT.format(
        persona_id=persona_id,
        scripts_section=_build_scripts_section(scripts),
        feedback_section=_build_feedback_section(feedback),
    )
    response = await provider.generate_text(prompt, schema=PersonaVote)
    data = json.loads(response)
    data["persona_id"] = persona_id  # Override — same defensive pattern as S1
    return PersonaVote(**data)
```

**Persona identity is prompt-injected.** The persona_id (e.g., "persona_42") is included in the prompt, and the LLM is asked to adopt that persona's perspective. Each persona votes independently — the prompt doesn't include other personas' votes.

**Top 5 selection:** each persona picks their top 5 scripts from the pool of 50. This is a ranking decision, not a binary accept/reject. The weighted scoring in S5 uses the position (1st vs 5th) to weight votes.

## S5: Rank (`s5_rank.py`)

**Input:** list of `PersonaVote`
**Output:** `S5Rankings` (top N scripts with vote counts and scores)
**LLM calls:** 0

```python
def s5_rank(votes: list[PersonaVote], top_n: int = 10) -> S5Rankings:
    score_weights = {0: 5, 1: 4, 2: 3, 3: 2, 4: 1}
    scores: Counter[str] = Counter()

    for vote in votes:
        for position, script_id in enumerate(vote.top_5_script_ids):
            scores[script_id] += score_weights.get(position, 1)

    top_scripts = scores.most_common(top_n)
    # ... build ranked list ...
```

**Borda count voting.** Position-weighted scoring is a form of Borda count — a voting system where each rank position gets a different number of points. It's more nuanced than simple plurality voting (just count first-place votes) because it considers the full ranking.

**`Counter.most_common(n)`** is Python's built-in way to find the N highest-scoring items. Implemented as a heap internally — O(n log k) where n is the total scripts and k is the top N.

## S6: Personalize (`s6_personalize.py`)

**Input:** one `CandidateScript` + `CreatorProfile`
**Output:** one `FinalResult` (personalized_script, video_prompt, original_script, rank, vote_score)
**LLM calls:** 1

```python
async def s6_personalize(script, profile, provider):
    creator_context = _build_creator_context(profile)
    prompt = S6_PERSONALIZE_PROMPT.format(
        hook=script.hook,
        body=script.body,
        payoff=script.payoff,
        tone=profile.tone,
        vocabulary=", ".join(profile.vocabulary),
        catchphrases=", ".join(profile.catchphrases),
        topics_to_avoid=", ".join(profile.topics_to_avoid),
        creator_context=creator_context,
        niche_instruction=niche_instruction,
    )
    response = await provider.generate_text(prompt, schema=S6Response)
    data = json.loads(response)

    # Handle LLM returning nested objects instead of strings
    video_prompt = data["video_prompt"]
    if isinstance(video_prompt, dict):
        video_prompt = json.dumps(video_prompt)
```

**Type coercion at the boundary.** The LLM sometimes returns `video_prompt` as a JSON object instead of a string. The code checks for this and serializes it back to a string. This is another defensive pattern — LLMs are nondeterministic in their output format, so validate and coerce at the boundary.

**Creator context as optional enrichment.** `_build_creator_context` adds niche, audience, themes, and example hooks to the prompt IF they exist in the profile. The `CreatorProfile` model has these as optional fields with defaults, so older profiles without them still work.

## The error hierarchy in practice

Across all stages, errors are structured:

```
S1 task catches:
├── json.JSONDecodeError → InvalidResponseError (LLM output is garbage)
├── InvalidResponseError → re-raise (already typed)
├── StageError → re-raise (already typed)
└── Exception → StageError (unknown failure, wrap it)

Task wrapper catches:
├── ProviderError → orchestrator.on_failure(recoverable=True)
├── StageError → orchestrator.on_failure(recoverable=False)
└── Exception → orchestrator.on_failure(recoverable=False)
```

**The hierarchy lets each layer handle what it can:** the stage function wraps parse failures, the task wrapper decides if the whole run should fail, the orchestrator publishes the error event. No layer handles errors it doesn't understand.

## The provider interface

All stage functions accept `provider: ReasoningProvider`, not `provider: KimiProvider` or `provider: GeminiProvider`. They call `provider.generate_text()` without knowing which LLM is behind it.

```python
class ReasoningProvider(Protocol):
    name: str
    async def generate_text(self, prompt: str, schema: type[BaseModel] | None = None) -> str: ...
    async def analyze_content(self, content: str, prompt: str) -> str: ...
```

This is the **Strategy pattern** — the algorithm (which LLM to call, how to format the request) varies, but the interface is fixed. Stage functions program to the interface, not the implementation.

## What you should take from this

1. **Pure functions are the most testable unit.** No infrastructure, no mocking Redis, no starting Celery. Just pass inputs, check outputs.

2. **Prompt → call → parse → validate is the canonical LLM integration pattern.** Learn it. Every LLM application follows some version of it.

3. **Override LLM outputs for fields you know.** If you have the correct video_id, don't trust the LLM to echo it correctly. Inject your known-good data after parsing.

4. **Use code for deterministic work, AI for creative work.** S2 and S5 are pure Python — no reason to involve an LLM in counting and sorting. Reserve LLM calls for tasks that require judgment, creativity, or language understanding.

5. **Type coercion at the boundary is normal.** LLMs are imprecise output machines. Expect strings that should be dicts, dicts that should be strings, missing fields, extra fields. Validate and coerce immediately after parsing.

---

***Next: [The Provider Abstraction](14-the-provider-abstraction.md) — the registry pattern, Protocol classes, and why the Gemini-to-Kimi switch was a one-line change.***
