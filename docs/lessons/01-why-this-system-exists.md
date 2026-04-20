# 1. Why This System Exists

> Every architecture is a response to constraints. Before you understand any system, understand what problem it's solving — and what forces shaped the solution.

## The product

Flair2 is an AI Script Studio for short-form video. A creator enters a profile — tone, niche, audience, catchphrases — and with one click the system returns **ten ready-to-shoot video scripts** to pick from. Under the hood it analyzes 100 real viral TikToks, extracts structural patterns, generates candidate scripts shaped by those patterns, has a panel of 42 personas vote, ranks the winners, and personalizes the top scripts into the creator's voice. The user watches the results appear in real time.

One click. Six stages. Roughly 260 LLM API calls. ~500,000 tokens of work. The user sees live progress as each stage completes.

That description — one click, many calls, live progress — is the entire reason a distributed architecture exists here. If it were one LLM call returning one result, you'd write a Python script.

## The three forces that shaped everything

When you look at any architecture, look for the **forces** — the constraints that made simpler designs impossible. Flair2 has three:

### Force 1: The work is slow

A full pipeline run takes 10-15 seconds. It makes hundreds of LLM API calls. If you put this work inside an HTTP request handler, the browser would time out, the server's connection pool would fill up with a handful of users, and you'd be scaling by the number of concurrent waits, not the number of concurrent computations.

**Implication:** the system that accepts requests must be different from the system that does the work. This is the fundamental split: API tier vs Worker tier.

### Force 2: The user needs live progress

A 15-second spinner is a terrible user experience. The user should see each stage complete in real time — the analysis finishing, the scripts being generated, each persona casting their vote. This means the backend needs to push events to the browser as work progresses.

**Implication:** you need a streaming channel from backend to frontend. The backend needs to publish events as stages complete, and the frontend needs to consume them without polling.

### Force 3: The work fans out

Within a single run, Stage 1 analyzes N videos concurrently (one LLM call per video). Stage 4 has M personas vote concurrently (one LLM call per persona). Stage 6 personalizes the top K scripts concurrently. These aren't sequential — they're parallel tasks that need to be coordinated.

**Implication:** you need a way to dispatch N concurrent tasks, track their completion, and trigger the next stage only when all N finish. This is the MapReduce pattern, and it requires a coordination mechanism.

## Why not simpler?

A useful discipline: before accepting a complex design, try to break it with simpler alternatives. Here are the three you'd try:

**"Just use async Python in one process."** FastAPI with `asyncio.create_task()` for each stage. This works for toy demos. It breaks because: (a) if the process dies, all in-flight work dies with it; (b) you can't scale API capacity independently of LLM throughput; (c) you're bottlenecked by one machine's resources.

**"Use a simple background job table in a database."** Write pending jobs to Postgres, poll from workers. This works and many production systems use it. Flair2 chose Celery + Redis because the project needed to demonstrate distributed systems concepts for a course (message queues, task routing, pub/sub). The database-polling approach is actually more reliable in many cases — but it doesn't teach you about brokers and workers.

**"Just poll from the frontend."** Instead of SSE streaming, the frontend could hit `GET /api/status` every 2 seconds. This works but wastes bandwidth, adds latency (up to 2 seconds of delay per event), and doesn't scale well to many concurrent watchers. SSE is strictly better for unidirectional server-to-client streaming.

Each simpler approach fails on at least one of the three forces. That's why the architecture is what it is.

## The two-person team

Flair2 was built by two people — Sam (pipeline + frontend) and Jess (infrastructure + distributed systems). This shaped the architecture:

- **Parallel tracks:** Sam could build stages S1-S6 and the frontend while Jess built Terraform, ECS, and Celery integration. The module boundaries are also team boundaries.
- **Interface contracts:** The API contract (documented in [GitHub issue #71](https://github.com/yangyang-how/flair2/issues/71)) was agreed upfront so both could work independently. When you see comments like `Contract: #71 Section 3` in the code, that's the seam where two people's work meets.
- **PR discipline:** Every PR required code review between Sam and Jess. One fix, one PR. No bundling unrelated changes.

This is how real engineering teams work: agree on interfaces, work in parallel, integrate through contracts. The architecture is shaped by the team as much as by the technology.

## What you should take from this

Three habits to build:

1. **Find the forces before reading the code.** Every architecture is shaped by constraints. If you understand "one click, many calls, live progress," you can predict most of Flair2's design before reading a line of code. This skill transfers to any system you'll ever read.

2. **Try to break it with simpler alternatives.** If a simpler design works, the complex one is unjustified. If a simpler design fails, you now understand *why* the complex one exists. Either way, you learn more from the exercise than from just reading the design.

3. **Every decision should name its failure mode.** "We use a task queue because..." should end with "...because in-process background tasks die with the process." If the sentence ends with "...because that's how it's done," you're cargo-culting.

---

***Next: [The Deployed Architecture](02-the-deployed-architecture.md) — the actual AWS topology, component by component.***
