---
description: Check if implementation matches the architecture design doc
---

## Design Document

Read the architecture doc:

!`cat design/architecture.md`

## Current Implementation

!`find backend -name '*.py' 2>/dev/null | head -30`
!`find app -name '*.py' 2>/dev/null | head -30`
!`find frontend -name '*.ts' -o -name '*.tsx' -o -name '*.astro' 2>/dev/null | head -30`
!`find site -name '*.ts' -o -name '*.tsx' -o -name '*.astro' 2>/dev/null | head -30`

## Review

Compare the implementation against the architecture doc:

1. Are pipeline stages (discovery, studio, evaluation) implemented as separate modules?
2. Is the MapReduce pattern used for audience evaluation (map = parallel workers, reduce = vote aggregation)?
3. Is Redis used for shared state and pub/sub, not just caching?
4. Are Celery tasks thin wrappers with logic in service modules?
5. Is the Gemini API accessed through a provider interface, not direct SDK imports?
6. Does SSE streaming work for pipeline status updates?
7. Are there any architectural decisions in code that contradict the design doc?

Report findings. If the design doc needs updating based on implementation learnings, suggest specific changes.
