# 23. The Frontend Stack

> The frontend is the simplest part of Flair2's architecture — by design. This article covers the technology choices, the islands architecture pattern, and why a static site was the right call.

## The stack

- **Astro** — static site generator with component islands
- **React 19** — interactive components (islands)
- **Framer Motion** — animations (pipeline visualizer, voting animation)
- **Tailwind CSS** — utility-first styling
- **S3** — static website hosting

**File:** `frontend/astro.config.mjs`

```javascript
export default defineConfig({
  output: "static",
  integrations: [react()],
});
```

`output: "static"` means the build produces plain HTML, CSS, and JavaScript files. No server-side rendering, no Node.js server in production. The build output is uploaded to S3 and served as static files.

## The islands architecture

Astro's key innovation is **islands architecture:** most of the page is static HTML (rendered at build time), and only the interactive parts are JavaScript components that "hydrate" in the browser.

```
┌─────────────────────────────────────────┐
│  Static HTML (Astro)                    │
│                                         │
│  ┌─────────────────┐  ┌──────────────┐ │
│  │  React Island    │  │ React Island │ │
│  │  (Pipeline Viz)  │  │ (Voting)     │ │
│  │  [interactive]   │  │ [interactive]│ │
│  └─────────────────┘  └──────────────┘ │
│                                         │
│  Static text, forms, layout...          │
│  [no JavaScript needed]                 │
└─────────────────────────────────────────┘
```

**Why this matters:** a traditional React SPA (Single Page Application) sends a large JavaScript bundle to the browser, which then renders everything client-side. Astro sends pre-rendered HTML for static content and small JavaScript bundles only for interactive components.

**Concrete benefit:** the landing page is static HTML — headings, descriptions, navigation. No JavaScript needed. The pipeline visualizer and voting animation are React components that need JavaScript for interactivity. Only those components are shipped as JS. The page loads fast because most of it is already HTML.

## The pages

```
frontend/src/pages/
├── index.astro      # Landing page — blob navigation to pipeline stages
├── create.astro     # Pipeline creation form
└── results.astro    # Results display
```

**`index.astro`:** the landing page with three blobs (Discover, Generate, Evaluate) that link to `/create`. Uses the V1 design language — rounded blobs with stage numbers, color-coded by pipeline phase. Pure static HTML + CSS.

**`create.astro`:** the pipeline creation form. The user enters creator profile details and selects a reasoning model. This page embeds a React island for the form (which needs JavaScript for dynamic validation and submission).

**`results.astro`:** displays pipeline results. Embeds React islands for the results view and voting animation (which need JavaScript for animations and SSE consumption).

## The React components

```
frontend/src/components/
├── PipelineVisualizer.tsx   # Real-time stage progress (SSE consumer)
├── VotingAnimation.tsx      # 100-persona voting visualization
├── ResultsView.tsx          # Final results display
├── CreateForm.tsx           # Pipeline creation form
└── ...
```

These are the interactive islands. They:
1. Open SSE connections to the backend
2. Parse incoming events
3. Update the UI in real time (React state + Framer Motion animations)

**The SSE integration** (conceptual):

```typescript
useEffect(() => {
    const evtSource = new EventSource(`/api/pipeline/status/${runId}`);
    evtSource.addEventListener('vote_cast', (event) => {
        const data = JSON.parse(event.data);
        setVoteCount(data.completed);
        // Animate the new vote
    });
    return () => evtSource.close();
}, [runId]);
```

The browser's native `EventSource` API handles SSE — connection management, reconnection, `Last-Event-ID` — for free. The React component just subscribes to events and updates state.

## V1 design language (PR #114, #115)

The V1 prototype had a distinctive visual style — rounded blobs, a custom color palette, specific typography. PR #114 ("feat: V1 design language — blobs, typography, color-coded pipeline") ported this visual identity to V2.

PR #115 ("feat: restyle ResultsView + VotingAnimation for V2 text-based output") adapted the V1 components for V2's different data shape: V1 generated images, V2 generates text scripts. The visual language (colors, shapes, animations) stayed the same; the content rendering changed.

**Design lesson:** the visual identity is a separate concern from the data rendering. V1's design language could be applied to V2's different content because the styling was in CSS/Tailwind, not hardcoded into the data display logic. Separation of presentation from content.

## Why S3, not a real hosting platform

**File:** `terraform/modules/frontend/main.tf`

The frontend is hosted on S3 with static website hosting enabled. The build output (`frontend/dist/`) is synced to S3 via `aws s3 sync`.

**Why S3 over CloudFront (CDN):** PR #107 simplified from S3 + CloudFront to S3-only. CloudFront adds caching, edge distribution, and custom domains. For a course project with limited traffic and no custom domain, S3 direct hosting is sufficient. CloudFront adds configuration complexity (cache invalidation, SSL certificates, origin access identity) that isn't justified at this scale.

**Why S3 over Cloudflare Pages:** the architecture doc mentions Cloudflare Pages. The `@astrojs/cloudflare` package is still in `package.json`. But deployment went to S3 because the rest of the infrastructure was on AWS — keeping everything in one cloud provider simplifies IAM, networking, and CI/CD.

**Why S3 over Vercel/Netlify:** these platforms are easier to set up (connect GitHub, auto-deploy). But Flair2's terraform-managed infrastructure approach requires all resources to be defined as code. S3 static hosting integrates naturally with the existing Terraform setup.

## The `crypto.randomUUID` fix (PR #121)

A fun edge case: the frontend used `crypto.randomUUID()` to generate session IDs. This API is only available in **secure contexts** (HTTPS or localhost). S3 static website hosting serves over HTTP, not HTTPS (unless you add CloudFront). On HTTP, `crypto.randomUUID()` is undefined.

PR #121 added a fallback: check if `crypto.randomUUID` exists, and if not, generate a UUID using `Math.random()`. This is less cryptographically secure but sufficient for session IDs in a prototype.

**The lesson:** browser APIs often have security context requirements that are invisible in development (where you're on `localhost`, a secure context) and only surface in production (where you might be on HTTP). Test in the same context you deploy to.

## Why not a full SPA

A Single Page Application (React Router, Next.js, etc.) would:
- Ship a large JavaScript bundle to every user
- Require client-side routing (more JavaScript)
- Need a Node.js server for SSR (server-side rendering) or use static export

Flair2 has three pages. Most content is static. Interactive components are concentrated in the pipeline visualizer and voting animation. The islands architecture gives you:
- Fast initial page load (static HTML, no JavaScript needed for content)
- Small JavaScript bundles (only interactive components are shipped)
- No Node.js server in production (static files on S3)
- SEO-friendly (content is in the HTML, not generated by JavaScript)

**Rule of thumb:** if your app is more than 80% static content with a few interactive widgets, use islands (Astro). If your app is highly interactive with client-side navigation (like a dashboard or email client), use a full SPA (Next.js, Remix).

## What you should take from this

1. **Islands architecture is the right default for content-heavy sites.** Most of the web is content, not interactivity. Ship HTML for content, JavaScript for interaction.

2. **Static output simplifies deployment.** No Node.js server, no containers, no port management. Just files on S3. The simplest deployment is the one with the fewest moving parts.

3. **Design language is separable from data rendering.** V1's visual identity applied to V2's different content because styling was in CSS, not in the data layer.

4. **Test in the deployment context.** Browser APIs that work on `localhost` may fail on HTTP in production. `crypto.randomUUID()` is the case study.

5. **The frontend is the least distributed part of the system.** It's static files served from a bucket. The complexity is in the backend. This is intentional — keep the frontend simple so you can focus engineering effort on the distributed systems challenges.

---

***Next: [Designing Distributed Systems Experiments](24-designing-experiments.md) — how to formulate hypotheses, choose variables, and interpret results.***
