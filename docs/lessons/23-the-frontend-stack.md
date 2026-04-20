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

**`index.astro`:** the landing page with three blobs (Discover, Generate, Evaluate) that link to `/create`. Rounded blobs with stage numbers, color-coded by pipeline phase. Pure static HTML + CSS.

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

## Design language lives in CSS, not in components

The frontend has a distinctive visual identity — rounded "blob" shapes for pipeline phases, custom typography pairings, a color palette keyed to each stage (Discover/Generate/Evaluate/Personalize). All of it is defined in Tailwind utility classes and CSS custom properties on `:root`, not baked into component JSX.

That separation matters: the voting animation, the pipeline visualizer, and the results view all render completely different data shapes, but they share one visual system. If a new view needs to be added — or an existing view needs to render a different payload — the styling doesn't have to be rewritten. Presentation and data rendering are independent concerns.

**Design lesson:** keep visual identity in the styling layer (CSS, Tailwind, design tokens) rather than hardcoding it into components. Components should render data; the style system should decide how it looks.

## Why S3, not a real hosting platform

**File:** `terraform/modules/frontend/main.tf`

The frontend is hosted on S3 with static website hosting enabled. The build output (`frontend/dist/`) is synced to S3 via `aws s3 sync`.

**Why S3 over CloudFront (CDN):** CloudFront adds caching, edge distribution, and custom domains — and a lot of operational surface (cache invalidation, SSL certificates, origin access identity). For a course project with limited traffic and no custom domain, S3 direct hosting is sufficient. The tradeoff would flip at real traffic or with a branded domain.

**Why S3 over Vercel/Netlify/Cloudflare Pages:** these platforms are faster to set up (connect GitHub, auto-deploy) but they sit outside the AWS infrastructure that Terraform manages for the rest of Flair2. Keeping everything in one cloud provider and one IaC tree simplifies IAM, networking, and CI/CD.

## The `crypto.randomUUID` fallback

The frontend generates client-side session IDs with `crypto.randomUUID()`. That API is only available in **secure contexts** (HTTPS or `localhost`). S3 static website hosting serves over plain HTTP unless you put CloudFront in front of it — so on the deployed site, `crypto.randomUUID` is `undefined`.

The client-side code guards for that:

```typescript
function generateSessionId(): string {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  // Fallback for non-secure contexts (S3 over HTTP)
  return "sess_" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}
```

Less cryptographically strong than `crypto.randomUUID`, but sufficient for session IDs in a prototype and — crucially — works on the deployment surface.

**The lesson:** browser APIs often have security-context requirements that are invisible in local development (where `localhost` counts as secure) and only surface in production. Test in the same context you deploy to, or guard for the feature at runtime.

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

3. **Design language is separable from data rendering.** Keep visual identity in CSS and design tokens, not baked into components. The same style system can render completely different data shapes.

4. **Test in the deployment context.** Browser APIs that work on `localhost` may fail on HTTP in production. `crypto.randomUUID()` is the case study.

5. **The frontend is the least distributed part of the system.** It's static files served from a bucket. The complexity is in the backend. This is intentional — keep the frontend simple so you can focus engineering effort on the distributed systems challenges.

---

***Next: [Designing Distributed Systems Experiments](24-designing-experiments.md) — how to formulate hypotheses, choose variables, and interpret results.***
