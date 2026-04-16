/**
 * Client-side wrapper for ResultsView.
 * Reads runId from the URL path instead of Astro.params.
 */

import { useRouteId } from "./RouteParam";
import ResultsView from "./ResultsView";
import { Spinner } from "./ui";

export default function ResultsPage() {
  const id = useRouteId(1); // /results/[id]

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
        <a href={`/pipeline/?id=${id}`} className="hover:text-[var(--color-text)]">Pipeline</a>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-text)]">Results</span>
      </nav>
      <ResultsView runId={id} />
    </div>
  );
}
