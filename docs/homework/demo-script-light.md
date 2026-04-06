# Flair2 Demo — Video Script (Light Theme)

**Target length:** ~2 minutes
**Slide deck:** `demo-light.html`
**Slide order:** Output → Problem → Pipeline → Architecture → Progress → Closing

---

## Before you record

Open `demo-light.html` in Chrome, fullscreen (`F11`). Navigate with arrow keys or clicks.
Keep the pace unhurried — two minutes is tight but not rushed.

---

## Script

### [Slide 1 — Output]

> "This is the output of our system."

*(pause — let the campaign cards load in)*

> "You give it a YouTube channel and a brand. It watches the videos, understands the content, identifies the audience — and generates a full, personalized campaign: copy, tone, visual direction, hashtags. Ready to post."

> "That's Flair2. Let me show you how it works."

---

### [Slide 2 — Problem] *(advance)*

> "Marketing teams spend hours writing content for every platform, every audience, every product. It's repetitive, it doesn't scale, and it's expensive."

> "We asked: what if an AI could watch your brand's videos and just — know what to say?"

---

### [Slide 3 — Pipeline] *(advance)*

> "Flair2 is a six-stage pipeline."

> "Stage one: discover — we scrape YouTube for relevant videos. Stage two: curate — we rank them. Stages three and four: brief generation — the AI writes a studio brief and a per-video brief. Stage five: assemble — we generate the campaign. Stage six: evaluate — the AI scores its own output."

> "Every reasoning stage runs on Kimi, Moonshot's frontier model. Fast, cheap, good."

---

### [Slide 4 — Architecture] *(advance)*

> "Under the hood: FastAPI backend, Celery task queue, Redis, deployed on AWS ECS Fargate — so it scales horizontally. Infrastructure is Terraform, CI is GitHub Actions. The whole thing is reproducible from a single `terraform apply`."

---

### [Slide 5 — Progress] *(advance)*

> "We're two milestones in. The core pipeline is done and running. AWS infrastructure is provisioned and tested. We're on track — M3 distributed processing starts next week."

---

### [Slide 6 — Closing] *(advance)*

> "Flair2. AI campaigns, from brand to brief to post."

> "Thanks."

---

## Timing guide

| Slide | Target |
|-------|--------|
| Output | 25s |
| Problem | 18s |
| Pipeline | 30s |
| Architecture | 20s |
| Progress | 15s |
| Closing | 10s |
| **Total** | **~2 min** |

---

## Notes

- Slide 1 is the hook — pause after "This is the output of our system." Let the audience read the cards before you keep talking.
- Slide 3 is the densest. Don't rush the stage names — they're the technical proof.
- Slide 4: say "ECS Fargate" clearly. It signals production-grade infrastructure to a technical audience.
- Closing is short on purpose. Don't fill silence with filler. Cut clean.
