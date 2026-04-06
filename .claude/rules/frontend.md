---
paths:
  - "frontend/**"
  - "site/**"
---
# Frontend Rules (Astro + React Islands)

- Use Astro components (.astro) for pages, layouts, and static UI.
- React islands (.tsx) only for interactive components: pipeline visualization, voting animation.
- Keep React islands minimal — they hydrate client-side and add to bundle size.
- Styles live in the styles/ directory. Use CSS custom properties for theming.
- Framer Motion for animations — keep animation logic in dedicated hooks or components.
- SSE event handling belongs in a dedicated hook (useSSE or similar), not inline in components.
- All API calls to the backend go through a single client module — no fetch() scattered across components.
- Run the build before committing to catch type errors and broken imports.
