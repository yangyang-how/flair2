/**
 * Client-side wrapper for VotingAnimation.
 * Reads runId from the URL path instead of Astro.params.
 */

import { useRouteId } from "./RouteParam";
import VotingAnimation from "./VotingAnimation";
import { Spinner } from "./ui";

export default function VotePage() {
  const id = useRouteId(1); // /vote/[id]

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
        <a href={`/pipeline/${id}`} className="hover:text-[var(--color-text)]">Pipeline</a>
        <span className="mx-2">/</span>
        <span className="text-[var(--color-text)]">Vote</span>
      </nav>
      <VotingAnimation runId={id} />
    </div>
  );
}
