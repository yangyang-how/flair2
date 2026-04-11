/**
 * Client-side wrapper for PipelineVisualizer.
 * Reads runId from the URL path instead of Astro.params.
 */

import { useRouteId } from "./RouteParam";
import PipelineVisualizer from "./PipelineVisualizer";
import { Spinner } from "./ui";

export default function PipelinePage() {
  const id = useRouteId(1); // /pipeline/[id]

  if (!id) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="py-4">
      <nav className="mb-6 text-sm text-[var(--color-text-muted)]">
        <a href="/" className="hover:text-[var(--color-text)]">Home</a>
        <span className="mx-2">/</span>
        <a href="/runs" className="hover:text-[var(--color-text)]">Runs</a>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-text)]">{id.slice(0, 8)}</span>
      </nav>
      <PipelineVisualizer runId={id} />
    </div>
  );
}
