# Flair2 Architecture & Systems Design — A Teaching Series

A 28-article curriculum that walks through a real distributed AI pipeline, from "what does this do" to "how would I design this myself." Written for someone who knows how to code but hasn't built distributed systems before.

By the end, you should be able to:
- Read an architecture diagram and identify which layer is failing
- Design a task queue pipeline with fan-out/fan-in coordination
- Choose the right communication pattern (SSE vs WebSocket vs polling)
- Reason about failure modes, rate limiting, and scaling
- Spot the difference between what design docs say and what code does

---

## Part I — Context

| # | Article | Core lesson |
|---|---------|-------------|
| 1 | [Why This System Exists](01-why-this-system-exists.md) | Every architecture is a response to constraints. Find the constraints first. |
| 2 | [The Deployed Architecture](02-the-deployed-architecture.md) | The real AWS topology — every component, what it does, and what's dormant. |
| 3 | [How to Read This Codebase](03-how-to-read-this-codebase.md) | Directory map, module boundaries, where to start. |

## Part II — The Request Path

| # | Article | Core lesson |
|---|---------|-------------|
| 4 | [The API Layer](04-the-api-layer.md) | Non-blocking request handling, dependency injection, route design. |
| 5 | [SSE and Redis Streams](05-sse-and-redis-streams.md) | Real-time server-to-client streaming, cursors, reconnection. |
| 6 | [The Request Lifecycle](06-the-request-lifecycle.md) | Following one click from browser to final result — connecting all the pieces. |

## Part III — The Task Queue

| # | Article | Core lesson |
|---|---------|-------------|
| 7 | [What Celery Is (and Isn't)](07-what-celery-is.md) | Broker, backend, worker — the mental model for task queues. |
| 8 | [Celery Configuration Deep Dive](08-celery-configuration.md) | `acks_late`, `prefetch_multiplier`, `task_track_started` — what each knob does. |
| 9 | [Worker Lifecycle and Failure](09-worker-lifecycle-and-failure.md) | What happens when a worker dies. Message redelivery, at-least-once, idempotency. |

## Part IV — The Pipeline

| # | Article | Core lesson |
|---|---------|-------------|
| 10 | [The Orchestrator State Machine](10-the-orchestrator.md) | Single-writer principle, stage transitions, counter-based fan-in. |
| 11 | [MapReduce: Fan-Out and Fan-In](11-mapreduce.md) | The counter pattern, distributed barriers, map stages vs reduce stages. |
| 12 | [Checkpoint and Recovery](12-checkpoint-and-recovery.md) | Crash recovery, exactly-once vs at-least-once, the economics of saved work. |
| 13 | [The Six Stage Functions](13-the-six-stages.md) | Pure functions, structured output, prompt-parse-validate, error hierarchies. |

## Part V — The Provider Layer

| # | Article | Core lesson |
|---|---------|-------------|
| 14 | [The Provider Abstraction](14-the-provider-abstraction.md) | Registry pattern, Protocol classes, coding to an interface with a real payoff. |
| 15 | [Kimi and OpenAI Compatibility](15-kimi-and-openai-compatibility.md) | API compatibility as an industry pattern, `default_headers`, provider migration. |
| 16 | [Rate Limiting a Shared Upstream](16-rate-limiting.md) | Token bucket, Redis INCR+EXPIRE, centralized vs distributed rate limiting. |

## Part VI — Redis

| # | Article | Core lesson |
|---|---------|-------------|
| 17 | [Redis as the Nervous System](17-redis-nervous-system.md) | Five roles, one server — the data model walkthrough. |
| 18 | [SETNX and Idempotency](18-setnx-and-idempotency.md) | Cache stampede prevention, the winner/loser pattern, sentinel TTLs. |
| 19 | [The Connection Pool Bottleneck](19-connection-pool-bottleneck.md) | Invisible resource exhaustion, same bug in two disguises, how to fix it. |

## Part VII — Infrastructure

| # | Article | Core lesson |
|---|---------|-------------|
| 20 | [Terraform and the AWS Topology](20-terraform-aws-topology.md) | VPC, subnets, security groups, IAM — reading infra-as-code as documentation. |
| 21 | [ECS Fargate: Two Services, One Cluster](21-ecs-fargate.md) | Why API and Worker scale independently, task definitions, autoscaling. |
| 22 | [CI/CD: The GitHub Actions Pipeline](22-cicd-github-actions.md) | Build-test-deploy, Docker lifecycle, deploy-then-test pattern. |
| 23 | [The Frontend Stack](23-the-frontend-stack.md) | Astro static + React islands, why not a full SPA, S3 website hosting. |

## Part VIII — Experiments

| # | Article | Core lesson |
|---|---------|-------------|
| 24 | [Designing Distributed Systems Experiments](24-designing-experiments.md) | Hypothesis, variables, controls, interpreting results — experimental method for systems. |
| 25 | [M5: Pipeline Resilience](25-m5-pipeline-resilience.md) | Backpressure, failure recovery, cache concurrency — what each proved. |
| 26 | [M5-4: Load Testing with Locust](26-m5-4-locust.md) | Locust, K=10 to K=500, the inflection point, auto-scaling under load. |
| 27 | [M6: ElastiCache Under Real Concurrency](27-m6-elasticache.md) | Latency, SETNX atomicity, memory — what unit tests hide. |
| 28 | [Cross-Experiment Findings](28-cross-experiment-findings.md) | Four findings that span experiments, the connection pool bottleneck, future work. |

---

## How to read this series

**Sequential is best.** Each article builds on the last. But if you're here for a specific topic, each Part is self-contained enough to read independently.

**Open the code alongside.** Every article references specific files and line numbers. The articles explain *why*; the code shows *how*. You need both.

**The insights matter.** Boxed insights (`***`) call out transferable principles — patterns you'll see again in completely different systems. These are the things that compound over time.

---

*Built from the Flair2 codebase at [github.com/yangyang-how/flair2](https://github.com/yangyang-how/flair2). Written by Shannon.*
