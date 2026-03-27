# Pipeline Quality Review — First Real Run

**Date:** 2026-03-27
**Run ID:** 4fb4c0fa-f20d-428c-8274-20b5e75c0429
**Data:** 100 Gopher-Lab transcripts (proven viral TikTok content)
**Test config:** 3 videos → 5 scripts → 5 personas → top 3 → 3 personalized results

---

## Verdict

**Architecture: Working.** All 6 stages chain correctly. Data flows from raw transcripts through pattern extraction, aggregation, generation, voting, ranking, and personalization. Error handling, retries, and JSON parsing recovery all function under real API conditions.

**Output quality: Insufficient.** Generated scripts are generic, lack specificity, and read like templates rather than content a real creator would produce. The pipeline proves *structure* can be extracted and applied, but the current prompts and data models don't capture what makes viral content actually compelling.

---

## Stage-by-Stage Analysis

### S1: Analyze — Pattern Extraction

**What it does well:**
- Correctly identifies structural categories (hook type, pacing, emotional arc)
- Extracts patterns from real transcripts, not hallucinated from metadata

**What's missing:**
- Extracts *labels* ("question + escalating") instead of *mechanics* (the specific rhetorical move in the first 3 seconds that creates a curiosity gap)
- Doesn't capture the *voice* of viral content — cadence, sentence rhythm, word choice patterns
- Ignores duration-to-content density ratio (a 9s video with a question hook works differently than a 60s one)
- Doesn't distinguish between patterns that drive *views* vs *comments* vs *shares* — these are different optimization targets
- Prompt asks "what is the hook_type?" — should ask "transcribe the exact opening words and explain why someone would stop scrolling"

**Suggested improvements:**
1. Extract verbatim hook text (first 2-3 sentences) alongside the classification
2. Add a `content_density` field (words per second) to inform S3 pacing
3. Add `engagement_driver` field — is this structured to drive saves (practical value), shares (social currency), or comments (controversy/opinion)?
4. Analyze the *transition* between hook → body → payoff, not just classify each section
5. Include audience inference — who is this video *for*?

### S2: Aggregate — Pattern Library

**What it does well:**
- Groups patterns by type with frequency counts
- Provides examples from source videos

**What's missing:**
- Loses the *specifics* during aggregation — "question + escalating" appears 2 times with 2 examples, but the nuance of each example is flattened into a category label
- No cross-pattern analysis — which combinations of hook + pacing + arc produce the highest engagement?
- No topic/niche clustering — patterns work differently in different content categories

**Suggested improvements:**
1. Preserve 2-3 verbatim hook examples per pattern type (not just pattern labels)
2. Add pattern co-occurrence matrix — which hook types pair with which pacing styles?
3. Weight patterns by source engagement quality if available
4. Cluster by content niche if S1 extracts audience/topic information

### S3: Generate — Script Creation

**What it does well:**
- Follows structural patterns from S2
- Produces complete hook/body/payoff scripts
- Distributes generation across pattern types proportional to frequency

**What's missing — this is the biggest quality gap:**
- **No topic/niche context.** Scripts are generated in a vacuum. A fitness creator and a cooking creator shouldn't get the same "phone battery hack" script. S3 needs to know *what the creator's channel is about*.
- **No audience awareness.** Who watches this creator? What problems do they have? What makes them share?
- **Generic hooks.** "Do you ever feel like..." is the most forgettable opening on TikTok. Real viral hooks are specific and unexpected.
- **No reference to source material.** S3 gets pattern labels but not the actual viral examples that worked. It should see *how* top creators executed the pattern, not just the pattern name.
- **Missing constraints.** No platform-specific length targets, no trend awareness, no seasonal context.

**Suggested improvements:**
1. Add `niche` and `target_audience` to the generation prompt (from creator profile)
2. Pass 2-3 verbatim hook examples from S2 as few-shot references
3. Add topic selection as an explicit step — either from creator input or inferred from their past content
4. Add "specificity score" as a self-evaluation — force the LLM to rate how generic its output is
5. Generate hooks independently first, then build scripts around the best hooks (hook quality is the #1 driver of views)

### S4: Vote — Persona Committee

**What it does well:**
- Multiple perspectives evaluate each script
- Top-5 ranking per persona creates meaningful signal
- Reasoning field captures why each persona voted the way they did

**What's missing:**
- **Personas have no identity.** `persona_0` through `persona_4` are blank slates. The LLM invents a persona each time with no consistency or grounding.
- **No audience modeling.** Personas should represent actual audience segments — demographics, content preferences, platform behavior patterns.
- **No calibration.** With no feedback data, personas vote based on the LLM's generic sense of "good content" rather than what actually performs.
- **All personas are essentially the same model.** 100 calls to the same LLM with the same prompt produce votes that correlate too highly — you get consensus, not diversity.

**Suggested improvements:**
1. Define 5-10 named persona archetypes with specific demographics, preferences, and viewing habits (e.g., "college student who watches during commute, saves practical tips, shares humor")
2. Give each persona a brief content preference history ("liked videos about X, skipped videos about Y")
3. Vary the voting prompt per persona type — a Gen Z viewer evaluates differently than a millennial parent
4. Consider using different temperature settings per persona to increase vote diversity
5. Once feedback data exists, calibrate persona preferences against actual video performance

### S5: Rank — Vote Aggregation

**What it does well:**
- Weighted scoring (5/4/3/2/1) is simple and effective
- Pure function, no LLM dependency, deterministic

**What's missing:**
- With homogeneous personas, ranking amplifies consensus bias rather than surfacing genuinely distinctive scripts
- No tiebreaking strategy beyond score ordering
- Doesn't distinguish between "everyone's #2" and "half love it, half hate it" — the latter might be more viral (polarization drives engagement)

**Suggested improvements:**
1. Add a `controversy_score` — scripts with high variance in persona rankings may outperform consensus picks
2. Report score distribution, not just total — a script ranked #1 by 3 personas and unranked by 2 tells a different story than one ranked #3 by all 5
3. This stage is fine mechanically — improvements depend on S4 producing more diverse votes

### S6: Personalize — Voice Injection

**What it does well:**
- Successfully rewrites scripts in creator's vocabulary and tone
- Generates detailed, production-ready video prompts with shot-by-shot breakdowns
- Handles LLM returning dicts instead of strings (robustness fix)

**What's missing:**
- **Creator profile is too shallow.** Tone + vocabulary + catchphrases is a caricature. Real voice adaptation needs: speaking rhythm, storytelling style, typical video structure, recurring themes, relationship with audience.
- **Over-applies vocabulary.** Every sentence gets "no cap" and "lowkey" — a real creator uses catchphrases selectively for emphasis, not as filler.
- **Video prompts are over-specified.** Shot-by-shot breakdowns for a 28-second TikTok are unrealistic. Creators work from loose concepts, not film scripts. The prompt should describe a *vibe* and key moments, not a storyboard.
- **No awareness of what the creator has already posted.** Personalization should avoid repeating topics/hooks from recent videos.

**Suggested improvements:**
1. Expand `CreatorProfile` with: niche, audience description, content themes, posting frequency, example video summaries, things that worked/flopped
2. Add instruction to use catchphrases sparingly (max 2-3 per script, at key moments)
3. Offer two video prompt formats: "quick concept" (3-5 lines for experienced creators) and "detailed brief" (full breakdown for production teams)
4. Cross-reference with creator's recent output to avoid repetition

---

## Cross-Cutting Issues

### Data Model Gaps
- `CreatorProfile` needs significant expansion (niche, audience, content history)
- `VideoInput.engagement` field is inconsistent between data sources (Gopher-Lab has `source`/`curated`, Trends has `views`/`completion_rate`)
- No concept of "campaign brief" — what is the creator trying to achieve with this batch of content?

### Feedback Loop (Not Yet Active)
The performance feedback loop (S3/S4 receiving past video metrics) is the designed solution for many quality issues. Once creators post videos and report results:
- S3 learns which topics/hooks actually performed
- S4 personas calibrate against real audience behavior
- S6 learns which personalization choices the creator accepted/rejected

This is M1-7+ territory but it's the mechanism that turns a mediocre first run into an improving system.

### Prompt Engineering Strategy
Current prompts are "tell me what category this is." They should be "show me what makes this work, using specific evidence from the content." The shift from classification to analysis is the single highest-leverage improvement.

---

## Priority Order for Quality Improvements

1. **S3 prompts + topic context** — Biggest impact. Generic scripts are the core quality problem.
2. **S1 prompts** — Deeper extraction feeds everything downstream.
3. **CreatorProfile expansion** — Garbage profile in, garbage personalization out.
4. **S4 persona definitions** — Diverse, grounded personas produce better voting signal.
5. **S6 prompt refinement** — Subtler vocabulary injection, flexible video prompt formats.
6. **S2 enrichment** — Preserve verbatim examples, add co-occurrence analysis.
7. **S5 controversy scoring** — Nice-to-have once S4 produces diverse votes.
