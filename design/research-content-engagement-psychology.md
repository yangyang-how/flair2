# Behavioral Psychology of Content Engagement

Research document for AI Campaign Studio V2. These models inform how the persona committee (S4/Evaluation stage) should evaluate generated campaigns and how the Studio stage should score scripts.

---

## 1. BJ Fogg's Behavior Model (B = MAP)

**Core principle:** Behavior = Motivation x Ability x Prompt. All three must converge at the same moment for a behavior to occur. If any element is missing, the behavior does not happen.

**Three components:**
- **Motivation** — The emotional drive. Fogg identifies three core motivators: sensation (physical pleasure/pain), anticipation (hope/fear), and belonging (social acceptance/rejection).
- **Ability** — How easy the behavior is to perform. Six factors: time, money, physical effort, mental effort (brain cycles), social deviance, and non-routine.
- **Prompt** — The trigger that initiates the behavior. Three types: Spark (boosts low motivation), Facilitator (reduces difficulty), Signal (reminder when both motivation and ability are high).

**Application to content engagement:**
- A "like" is the lowest-ability action — one tap, zero cognitive cost. Platforms maximize this by placing the button directly below content (prompt) when emotional reaction peaks (motivation).
- Sharing requires higher ability (choosing who to share with, social risk of endorsement) so it demands higher motivation — content must provoke strong emotion to clear the threshold.
- Commenting has the highest ability cost (typing, formulating thoughts) so it requires either very high motivation (strong opinion) or a facilitator prompt (e.g., "What do you think?" in the caption).
- Scrolling itself is designed for near-zero ability cost — infinite scroll eliminates the "next page" friction entirely.

**Implication for persona committee:** Each simulated persona should have a motivation profile (what drives them) and an ability threshold (how much friction they tolerate). Content that clears both thresholds for a specific persona predicts engagement from that demographic.

Sources:
- [Fogg Behavior Model (Official)](https://www.behaviormodel.org/)
- [Fogg Behavior Model — Stanford Behavior Design Lab](https://behaviordesign.stanford.edu/resources/fogg-behavior-model)
- [Fogg Behavior Model — The Decision Lab](https://thedecisionlab.com/reference-guide/psychology/fogg-behavior-model)
- [Fogg Behavior Model — Northbeam](https://www.northbeam.io/blog/fogg-behavior-model-motivation-ability-and-prompts)

---

## 2. Nir Eyal's Hook Model

**Core principle:** Habit-forming products cycle users through four phases: Trigger -> Action -> Variable Reward -> Investment. Each cycle strengthens the habit.

**Four phases:**
1. **Trigger** — External (notification, ad, recommendation) or internal (boredom, loneliness, FOMO). Internal triggers are more powerful because they don't require external stimulus.
2. **Action** — The simplest behavior in anticipation of reward. Must be low-friction (Fogg's ability principle applies here). Opening the app, swiping to the next video.
3. **Variable Reward** — The key mechanism. Unpredictable rewards activate the dopamine system more powerfully than predictable ones. Three types:
   - **Rewards of the Tribe** — Social validation (likes, comments, followers, status).
   - **Rewards of the Hunt** — Information, resources, deals — the "search and find" satisfaction.
   - **Rewards of the Self** — Mastery, completion, competence — intrinsic satisfaction.
4. **Investment** — User puts something in (content, data, followers, watch history) that improves the next cycle. This increases switching cost and personalizes future triggers.

**TikTok as the perfect Hook implementation:**
- Trigger: Push notifications + internal boredom cues
- Action: Open app, content plays immediately with zero friction
- Variable Reward: Every swipe delivers unpredictable content (tribe + hunt + self rewards all present)
- Investment: Watch history trains the algorithm, making future rewards more relevant

**Implication for script evaluation:** The best campaign content should embed hooks — it should trigger emotional responses (not just inform), deliver variable reward (surprise, delight, revelation), and invite investment (follow for more, save for later, comment your experience).

Sources:
- [Hook Model — UserGuiding](https://userguiding.com/blog/hook-model)
- [Understanding the Hook Model — Dovetail](https://dovetail.com/product-development/what-is-the-hook-model/)
- [Variable Rewards — Nir Eyal (NirAndFar)](https://www.nirandfar.com/want-to-hook-your-users-drive-them-crazy/)
- [Hook Model — Amplitude](https://amplitude.com/blog/the-hook-model)
- [Hook Model — Mindtools](https://www.mindtools.com/aapqtdb/the-hook-model-of-behavioral-design/)

---

## 3. Kahneman's System 1 vs System 2 Thinking

**Core principle:** The brain has two processing modes. System 1 is fast, automatic, intuitive, and effortless. System 2 is slow, deliberate, analytical, and effortful. Most social media consumption happens in System 1.

**Why this matters for content:**
- Social media browsing is a System 1 activity. Users scroll in a relaxed, low-effort state seeking "cognitive ease" — not intellectual challenge.
- Content that requires System 2 processing (complex arguments, dense information, nuanced takes) creates friction. The default System 1 response to friction is to scroll past.
- Viral content succeeds because it appeals to System 1: strong visuals, simple messages, emotional triggers, familiar patterns, bold/uppercase text.
- System 1 is susceptible to cognitive biases — anchoring, framing, availability heuristic — which is why emotionally charged content spreads faster than factual content.

**The "cognitive ease" spectrum:**
- High cognitive ease (System 1 friendly): clear visuals, repeated exposure, simple language, primed emotions, good mood -> feels true, feels good, feels familiar -> engagement.
- Low cognitive ease (triggers System 2): unfamiliar format, complex language, cognitive dissonance -> feels effortful, feels suspicious -> scroll past.

**Implication for script evaluation:** Score scripts on "System 1 friendliness." Can the core message be grasped in under 3 seconds? Does it lead with emotion rather than information? Does it use familiar formats and visual patterns? Content that forces System 2 processing in a System 1 environment will underperform regardless of quality.

Sources:
- [System 1 and System 2 Thinking — The Decision Lab](https://thedecisionlab.com/reference-guide/philosophy/system-1-and-system-2-thinking)
- [System 1 and System 2 Thinking — The Marketing Society](https://www.marketingsociety.com/think-piece/system-1-and-system-2-thinking)
- [How Viral Social Media Posts Undermine Critical Thinking — Psychology Today](https://www.psychologytoday.com/au/blog/the-art-of-critical-thinking/202504/how-viral-social-media-posts-undermine-critical-thinking)
- [Sharing Fast and Slow — Nieman Lab](https://www.niemanlab.org/2013/11/sharing-fast-and-slow-the-psychological-connection-between-how-we-think-and-how-we-spread-news-on-social-media/)

---

## 4. The Mere Exposure Effect

**Core principle:** People develop preference for things simply because they are familiar with them. Discovered by Robert Zajonc (1968). The mechanism is "processing fluency" — familiar stimuli are processed more easily by the brain, which registers as a positive feeling.

**Key dynamics:**
- The effect follows an inverted U-curve: liking increases with exposure up to 10-20 presentations, then plateaus, and eventually declines (irritation/boredom).
- Exposure without negative consequences builds trust. The brain associates repeated safe encounters with safety.
- Works even with subliminal exposure — conscious awareness is not required.

**Application to social media marketing:**
- Consistent posting builds brand familiarity, which registers as preference even before the audience consciously evaluates the content.
- Visual consistency (colors, fonts, editing style) across posts compounds the effect — each post reinforces processing fluency from previous ones.
- The inverted U-curve explains why over-posting or running the same ad too long causes audience fatigue.

**Implication for campaign design:** Campaign output should maintain visual and tonal consistency across assets. The persona committee should model the exposure curve — early impressions build familiarity, but the campaign plan should account for creative refresh before the decline phase hits.

Sources:
- [Mere-Exposure Effect — Wikipedia (Zajonc 1968)](https://en.wikipedia.org/wiki/Mere-exposure_effect)
- [Mere-Exposure Effect in Marketing — Jenosize](https://www.jenosize.com/en/ideas/real-time-marketing/mere-exposure-effect)
- [Mere Exposure Effect on Social Media — ImagiBrand](https://imagibrand.com/will-mere-exposure-to-a-brand-on-social-media-make-me-like-it-more/)
- [Mere Exposure Effect — Cognitive Clicks](https://cognitive-clicks.com/blog/mere-exposure-effect/)

---

## 5. Social Proof and the Bandwagon Effect

**Core principle:** People look to others for cues on how to behave, especially in uncertain situations. When visible signals show that many others have engaged with content, new viewers are more likely to engage as well.

**Mechanisms:**
- **Social proof** — "If others are doing it, it must be correct/good." Visible engagement metrics (likes, views, comments) serve as endorsement signals.
- **Bandwagon effect** — The tendency to align beliefs and behaviors with the majority. The more people join, the stronger the pull for others to follow.
- **Feedback loop** — High engagement -> more visibility (algorithm boost) -> more viewers -> more engagement. This is why early engagement velocity matters so much.

**Evidence:**
- A Spiegel Research Group study found 92% of online shoppers read reviews before purchasing, with positive reviews significantly influencing decisions.
- Social media platforms explicitly display engagement counts as social proof signals — view counts, like counts, comment counts all serve this function.
- Trending hashtags and viral challenges exploit the bandwagon effect: participation signals group membership.

**Implication for persona committee:** Social proof dynamics should be modeled in evaluation. Content that is likely to generate visible early engagement (comments, shares) will benefit from a compounding social proof effect. The committee should weight "engagement velocity potential" — will this content generate fast initial engagement that triggers the feedback loop?

Sources:
- [Bandwagon Effect — Renascence](https://www.renascence.io/journal/bandwagon-effect-leveraging-social-proof-in-customer-experience)
- [Psychology of Social Media Engagement — Qualia Academy](https://qualia-academy.co.uk/psychology-of-social-media-engagement/)
- [Social Proof — Optimizely](https://www.optimizely.com/optimization-glossary/social-proof/)
- [Social Proof — Media Theory](https://mediatheory.net/social-proof/)

---

## 6. Cialdini's Reciprocity Principle

**Core principle:** People feel compelled to return favors and honor obligations. When someone provides value first, the recipient feels a psychological obligation to give something back.

**Application to content creators:**
- Creators who consistently provide free value (entertainment, education, tips, emotional support) build a "reciprocity debt" with their audience.
- Audiences reciprocate through engagement (likes, comments, shares), loyalty (following, watching consistently), and commerce (purchasing recommended products, using affiliate links).
- Exclusive offers (discount codes, early access) strengthen reciprocity — the audience perceives the creator went out of their way, increasing obligation to reciprocate.
- Platforms engineer reciprocity loops: likes beget likes, comments invite responses, follows suggest follow-backs.

**The value-first strategy:**
- Content that gives before it asks outperforms content that asks immediately.
- Tutorial content, free resources, entertainment — all create reciprocity that can be converted later.
- This explains why "value-add" content strategies (teach something, then sell) outperform direct promotion.

**Implication for campaign scripts:** Campaign content should lead with value delivery (entertainment, information, emotional resonance) before any brand message or CTA. The persona committee should evaluate: "Does this content give the viewer something before asking for something?"

Sources:
- [Psychology of Influencer Marketing — Zion & Zion](https://www.zionandzion.com/the-psychology-of-influencer-marketing-using-cialdinis-principles-of-persuasion/)
- [Cialdini's 7 Principles — Neurofactor](https://neurofactor.nl/influence-the-7-principles-of-cialdini/)
- [Reciprocity Principle — Cognitigence](https://www.cognitigence.com/blog/principle-of-reciprocity-norm)
- [Cialdini's Principles Applied to Online Platforms — Gaia Digital](https://www.gaiadigital.nl/en/7-principles-of-persuasion-applied-to-online-platforms/)

---

## 7. Self-Determination Theory (SDT)

**Core principle:** Humans have three basic psychological needs — autonomy, competence, and relatedness. When these needs are satisfied, people experience intrinsic motivation, well-being, and sustained engagement. When thwarted, motivation and engagement decline.

**The three needs:**
- **Autonomy** — The need to feel in control of one's own choices and behaviors. On social media: choosing what to watch, who to follow, what to create.
- **Competence** — The need to feel effective and capable. On social media: mastering a trend, creating content that gets engagement, learning new skills from tutorials.
- **Relatedness** — The need to feel connected to others. On social media: belonging to communities, receiving responses, shared experiences.

**Why people create content (SDT lens):**
- Autonomy: Self-expression, choosing what to share, controlling one's narrative.
- Competence: Demonstrating expertise, gaining followers as validation of skill, improving craft.
- Relatedness: Building community, connecting with like-minded people, receiving feedback.

**Why people engage with content (SDT lens):**
- Autonomy: Curating their own feed, choosing what to engage with.
- Competence: Learning something new, feeling "in the know."
- Relatedness: Feeling part of a community, connecting with the creator.

**Implication for persona committee:** Each simulated persona should have weighted SDT needs. A "competence-driven" persona engages with educational/tutorial content. A "relatedness-driven" persona engages with community and emotional content. A "autonomy-driven" persona engages with content that empowers choice or self-expression.

Sources:
- [Self-Determination Theory — Official Site](https://selfdeterminationtheory.org/theory/)
- [Ryan & Deci (2000) — SDT Foundational Paper](https://selfdeterminationtheory.org/SDT/documents/2000_RyanDeci_SDT.pdf)
- [Self-Determination Theory — Wikipedia](https://en.wikipedia.org/wiki/Self-determination_theory)
- [SDT and Social Media — Nature](https://www.nature.com/articles/s41599-024-03150-x)

---

## 8. Parasocial Relationships

**Core principle:** Viewers develop one-sided feelings of intimacy, friendship, and loyalty toward media figures they have never met. Coined by Horton & Wohl (1956). Social media has dramatically intensified this phenomenon.

**How parasocial relationships form:**
- **Self-disclosure** — Creators share personal details, struggles, daily routines. This creates an illusion of mutual intimacy even though information flow is one-directional.
- **Direct address** — Speaking to camera, using "you," responding to comments. Creates the feeling of conversation.
- **Consistency** — Regular posting builds routine. Viewers feel the creator is "always there," similar to a friend.
- **Perceived authenticity** — "Behind the scenes" content, unpolished moments, admitting mistakes. Signals realness that deepens perceived connection.

**Why this drives engagement:**
- Parasocial bonds generate loyalty that mirrors real relationships — viewers defend creators, feel hurt by perceived betrayals, and experience genuine grief when creators leave platforms.
- Social media platforms reward engagement signals (comments, watch-time, duets), so creators who build parasocial intimacy rise in algorithmic rankings, creating a reinforcing cycle.
- The "one-and-a-half sided" nature of social media (unlike traditional broadcast) makes it more potent — occasional replies or acknowledgments give audiences just enough reciprocity to sustain the illusion.

**Implication for campaign design:** Campaign content that establishes parasocial elements (direct address, vulnerability, personal narrative) will generate stronger audience retention and loyalty than purely informational content. The persona committee should assess: "Would this content make the viewer feel personally connected to the creator?"

Sources:
- [Parasocial Interaction — Wikipedia (Horton & Wohl 1956)](https://en.wikipedia.org/wiki/Parasocial_interaction)
- [Parasocial Relationships — Psychology Today](https://www.psychologytoday.com/us/basics/parasocial-relationships)
- [What Parasocial Relationships Do to Our Brains — National Geographic](https://www.nationalgeographic.com/science/article/parasocial-relationships-social-media)
- [Parasocial Relationships — Encyclopedia MDPI](https://encyclopedia.pub/entry/36306)
- [Parasocial Interaction — Britannica](https://www.britannica.com/science/parasocial-interaction)

---

## 9. Cognitive Load Theory

**Core principle:** Working memory has limited capacity. When content exceeds that capacity (high cognitive load), comprehension and engagement drop. Developed by John Sweller (1988).

**Three types of cognitive load:**
- **Intrinsic load** — Inherent complexity of the information itself.
- **Extraneous load** — Unnecessary complexity from poor presentation (cluttered visuals, confusing structure, competing elements).
- **Germane load** — Productive mental effort directed at understanding and integrating information.

**Why simple content wins on social media:**
- Social media creates continuous "micro-cognitive loads" — each post competes for limited working memory resources.
- The first sentence/second determines whether users invest cognitive resources in the rest.
- One concept per post outperforms multi-concept posts.
- Research shows that social media use itself induces measurable cognitive load because users must hold multiple evaluation schemas in working memory (is this entertaining? is this relevant? who posted this? should I engage?).

**Design principles for low cognitive load:**
- Progressive disclosure: lead with the hook, reveal details incrementally.
- Visual hierarchy: one focal point, not competing elements.
- Text overlays should enhance, not complicate, image comprehension.
- Short paragraphs, bullet points, and subheadings reduce load in text-heavy content.

**Implication for script evaluation:** Scripts should be scored on cognitive load. How many concepts are introduced? How quickly is the core message clear? Is the visual composition focused or cluttered? The persona committee should penalize scripts that require high cognitive effort in the first 3 seconds.

Sources:
- [Cognitive Load Theory in Content Strategy — Winsome Marketing](https://winsomemarketing.com/winsome-marketing/cognitive-load-theory-in-content-strategy-why-less-information-converts-more)
- [Cognitive Load Theory — The Decision Lab](https://thedecisionlab.com/reference-guide/psychology/cognitive-load-theory)
- [Cognitive Load and Social Media Advertising — Journal of Interactive Advertising](https://www.tandfonline.com/doi/abs/10.1080/15252019.2022.2144780)
- [Cognitive Load — Wikipedia](https://en.wikipedia.org/wiki/Cognitive_load)

---

## 10. The Zeigarnik Effect

**Core principle:** People remember incomplete or interrupted tasks better than completed ones. Discovered by Bluma Zeigarnik (1927). Incomplete information creates psychological tension that persists until resolution is achieved.

**How it drives content engagement:**
- **Cliffhangers** — Ending a video mid-story ("Part 2 drops tomorrow") keeps the audience psychologically invested. The unresolved tension ensures they return.
- **Open loops** — Starting with a provocative question or half-answer ("There's one trick that worked for me — but it's not what you think") captures and holds attention because the brain demands closure.
- **Series content** — Multi-part content creates ongoing cognitive bookmarks. Each installment resolves one loop while opening another.
- **A University of California study found cliffhangers increased time-on-page by over 45% on average.**

**Risks of overuse:**
- Audiences become frustrated if payoffs are consistently unsatisfying (the "clickbait problem").
- Over-reliance on open loops without resolution erodes trust.
- The effect works best when the incomplete element is genuinely interesting, not artificially withheld.

**Implication for campaign scripts:** Scripts should be evaluated for strategic incompleteness. Does the content create a reason to come back? Does it open a loop that resolves satisfyingly while hinting at more? The persona committee should assess "return motivation" — after watching, does the viewer have a reason to seek out more from this brand?

Sources:
- [Zeigarnik Effect in Marketing — Lead Alchemists](https://www.leadalchemists.com/marketing-psychology/ziegarnik-effect/)
- [Zeigarnik Effect for Engaging Storytelling — PodIntelligence](https://www.podintelligence.com/blog/zeigarnik-effect-for-engaging-storytelling/)
- [How the Zeigarnik Effect Hooks Us on Social Media — Medium](https://medium.com/@ruchakher/unfinished-addictive-how-the-zeigarnik-effect-hooks-us-on-social-media-9305c4eca3cd)
- [Zeigarnik Effect — Learning Loop](https://learningloop.io/plays/psychology/zeigarnik-effect)

---

## 11. Hedonic Adaptation

**Core principle:** Humans become less sensitive to repeated stimuli over time, whether positive or negative. The same content that once excited an audience will eventually feel routine and boring. This forces creators into an escalation treadmill.

**The content creator's dilemma:**
- What worked last month produces diminishing returns this month. Audiences habituate to formats, styles, jokes, and production quality.
- Creators must continuously introduce novelty — new formats, higher production value, unexpected angles, fresh collaborations — to maintain the same engagement level.
- This is why platforms see format cycles: a new content format emerges, gets copied widely, audiences habituate, and a new format must replace it.

**Strategies to manage hedonic adaptation:**
- **Novelty injection** — Regularly introduce new elements that surprise and delight.
- **Format rotation** — Cycle between content types rather than repeating one format.
- **Social audience effect** — Research shows that perceived admiration from others can slow hedonic adaptation. Shared experiences feel fresher than solitary ones.
- **Core message + novel delivery** — The underlying brand message can stay consistent while the creative execution varies. This combines mere exposure (consistency) with hedonic adaptation management (novelty).

**Implication for campaign design:** Campaign plans should include creative variation built in from the start, not as an afterthought. The persona committee should model audience fatigue — a campaign that looks identical across all assets will score lower than one with consistent messaging but varied creative execution.

Sources:
- [Hedonic Adaptation in Marketing — Marketing Week](https://www.marketingweek.com/the-principle-of-hedonic-adaptation-lets-brands-reuse-core-messages-in-novel-ways/)
- [Hedonic Adaptation in UX — UX Bulletin](https://www.ux-bulletin.com/hedonic-adaptation-in-ux-designing-for-sustained-delight/)
- [All Eyes on You: Social Audience and Hedonic Adaptation — Wiley](https://onlinelibrary.wiley.com/doi/abs/10.1002/mar.21401)
- [Hedonic Adaptation — InsideBE](https://insidebe.com/articles/hedonic-adaptation-everything-you-need-to-know/)

---

## 12. Psychology of Engagement Actions: Like vs Comment vs Share vs Save

Each engagement action reflects a different psychological motivation. They are NOT interchangeable signals.

### LIKE — Low-effort validation
- **Psychology:** Dopamine-driven micro-reward. The lowest-friction form of social acknowledgment.
- **What triggers it:** Emotional resonance (positive or negative), social proof (everyone else liked it), brand affinity, parasocial reciprocity ("I like this creator").
- **Cognitive cost:** Near zero. System 1. Reflexive.
- **What it signals:** "I noticed this and felt something." It's a social bookmark more than a deep endorsement.
- **Research finding:** Likes and reactions are primarily driven by brand relationship connections (Springer study on social media engagement choices).

### COMMENT — Identity expression and conversation
- **Psychology:** Need for self-expression, social connection, and visibility. Commenting is a public performance — it signals the commenter's identity to the creator and to other viewers.
- **What triggers it:** Strong opinion, desire to be seen, direct prompt from creator ("What do you think?"), disagreement, humor opportunity, relatedness need (SDT).
- **Cognitive cost:** Moderate to high. Requires System 2 engagement — formulating and typing a response.
- **What it signals:** "This content moved me enough to invest effort in responding." Comments are driven by both brand relationship AND self-presentation (Goffman's impression management).
- **Research finding:** Comments are the strongest signal of deep engagement and predict long-term audience retention.

### SHARE — Identity signaling and relationship maintenance
- **Psychology:** Sharing is fundamentally about the sharer's identity, not the content itself. People share to define themselves to others, maintain relationships, and support causes they care about.
- **What triggers it:** High-arousal emotions (joy, anger, surprise, awe), identity alignment ("this represents who I am"), utility ("my friend needs to see this"), social currency ("I found this first").
- **Cognitive cost:** Moderate. Requires choosing a recipient and accepting social risk (what does sharing this say about me?).
- **What it signals:** "This content is worth associating my identity with."
- **NYT Customer Insight Group study (2,500 participants) identified five sharing motivations:** (1) bring valuable/entertaining content to others, (2) define ourselves to others, (3) grow and nourish relationships, (4) self-fulfillment, (5) support causes and brands.
- **Six sharer personas identified:** Altruists, Careerists, Hipsters, Boomerangs, Connectors, Selectives — each with different motivations and preferred content types.

### SAVE — Personal utility and future intent
- **Psychology:** Saving is a private, self-directed action. Unlike likes, comments, and shares — which are all social — saving is personal curation. It satisfies the need for organization, planning, and future self-improvement.
- **What triggers it:** Practical utility ("I'll need this later"), aspiration ("I want to be/do this"), information density (too much to absorb now), purchase intent ("I'm considering this").
- **Cognitive cost:** Low to moderate. Requires a judgment of future value, not just present emotional response.
- **What it signals:** "This content has lasting value beyond the moment." Saves indicate the content transcends entertainment into utility.
- **Research finding:** Saves are the strongest signal of content value because they represent deliberate future intent. Content optimized for saves (tutorials, references, checklists, inspiration boards) has longer effective lifespan than content optimized for likes.

### Summary Matrix

| Action  | Cognitive Cost | Primary Driver              | Signal Type     | Psychological Need (SDT) |
|---------|---------------|----------------------------|-----------------|--------------------------|
| Like    | Very low      | Emotional resonance        | Social/reflexive| Relatedness             |
| Comment | High          | Self-expression, opinion   | Identity/social | Autonomy, competence    |
| Share   | Moderate      | Identity signaling         | Public/social   | Relatedness, autonomy   |
| Save    | Low-moderate  | Personal utility, aspiration| Private/self   | Competence              |

### Implication for persona committee
Each simulated persona should produce differentiated engagement predictions — not just "will they engage" but "how will they engage." A persona representing a professional audience might predict high saves and shares but low comments. A persona representing a community-oriented audience might predict high comments but low saves. This differentiation makes the evaluation output actionable for campaign strategy.

Sources:
- [Psychology of Likes, Comments, and Shares — David Hopkins](https://www.dontwasteyourtime.co.uk/social-network/the-psychology-of-likes-comments-and-shares/)
- [Psychology of Social Media Engagement — MultiPost Digital](https://www.multipostdigital.com/blog/4w586oxvkv8m8rvqqjwgsqk0u8n85j)
- [Like, Comment, or Share? Self-Presentation vs. Brand Relationships — Springer](https://link.springer.com/article/10.1007/s11002-020-09518-8)
- [Psychology of Social Media — Buffer](https://buffer.com/resources/psychology-of-social-media/)
- [NYT Psychology of Sharing Study — Business Wire](https://www.businesswire.com/news/home/20110713005971/en/The-New-York-Times-Completes-Research-on-%E2%80%98Psychology-of-Sharing%E2%80%99)
- [Psychology Behind Bookmarks on Social Media — Robert Katai](https://robertkatai.com/the-psychology-behind-bookmarks-on-social-media/)
- [What Do Instagram Saves Say About You? — Stylist](https://www.stylist.co.uk/life/save-instagram-photo-video-meaning/609418)

---

## Synthesis: How These Models Inform the Persona Committee (S4)

### Evaluation Dimensions

Drawing from all 12 models, the persona committee should evaluate campaign content on these dimensions:

1. **System 1 Accessibility** (Kahneman) — Is the core message graspable in under 3 seconds? Does it lead with emotion?
2. **Motivation-Ability Fit** (Fogg) — For the target audience, does motivation exceed the effort required for the desired action?
3. **Hook Strength** (Eyal) — Does the content contain a variable reward? Does it invite investment?
4. **Cognitive Load** (Sweller) — Is it one concept, clearly presented? Or cluttered and demanding?
5. **Parasocial Warmth** (Horton & Wohl) — Does the content create personal connection? Direct address, vulnerability, authenticity?
6. **Social Proof Potential** (Cialdini) — Will early engagement generate visible signals that compound?
7. **Share Trigger** (NYT Study / Goffman) — Does the content serve identity signaling? Would someone share this to define themselves?
8. **Return Hook** (Zeigarnik) — Does the content create a reason to come back? Strategic incompleteness?
9. **Reciprocity Balance** (Cialdini) — Does it give value before asking for anything?
10. **Novelty vs Familiarity** (Mere Exposure + Hedonic Adaptation) — Is it fresh enough to avoid habituation but consistent enough to build brand recognition?
11. **SDT Need Satisfaction** (Deci & Ryan) — Does it satisfy autonomy, competence, or relatedness for the target persona?
12. **Engagement Type Prediction** — Will this drive likes, comments, shares, or saves? Which is most valuable for the campaign goal?

### Persona Design Principles

Each simulated persona in the committee should have:
- A **motivation profile** (Fogg's three motivators, weighted)
- A **primary SDT need** (autonomy, competence, or relatedness)
- A **content processing mode** (System 1 dominant vs System 2 tolerant)
- A **parasocial susceptibility** score (how much they value creator connection)
- A **sharing persona** (from NYT study: Altruist, Careerist, Hipster, Boomerang, Connector, Selective)
- An **engagement action tendency** (like-heavy, comment-heavy, share-heavy, save-heavy)
- A **hedonic adaptation rate** (how quickly they fatigue on repeated stimuli)

This gives the committee structured, psychologically grounded dimensions for evaluating whether generated content will actually drive real engagement — not just look good on paper.
