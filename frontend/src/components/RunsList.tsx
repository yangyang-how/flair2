/**
 * Runs List — shows previous pipeline runs for the current session.
 *
 * Uses /api/runs; entries link to /pipeline/?id=... (live/failed) or
 * /results/... (completed).
 */

import { useEffect, useState } from "react";
import { listRuns, type RunStatus } from "../lib/api-client";

function statusColor(status: string): string {
  switch (status) {
    case "completed":
      return "var(--color-success)";
    case "failed":
      return "var(--color-error)";
    case "running":
      return "var(--disc-a)";
    default:
      return "var(--color-text-muted)";
  }
}

function linkFor(run: RunStatus): string {
  // Query-string form, not path — S3 static hosting only pre-generates
  // the bare /results/ and /pipeline/ routes; any path-style ID 404s
  // and falls through to the index.html error document.
  if (run.status === "completed") return `/results/?id=${run.run_id}`;
  return `/pipeline/?id=${run.run_id}`;
}

export default function RunsList() {
  const [runs, setRuns] = useState<RunStatus[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const resp = await listRuns();
        if (!cancelled) setRuns(resp.runs);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <p className="font-ui text-sm text-[var(--color-error)]">
        Failed to load runs: {error}
      </p>
    );
  }

  if (runs === null) {
    return (
      <p className="font-ui text-sm text-[var(--color-text-muted)]">Loading…</p>
    );
  }

  if (runs.length === 0) {
    return (
      <div className="space-y-2">
        <p className="font-ui text-sm text-[var(--color-text-muted)]">
          No runs yet for this session.
        </p>
        <a
          href="/create"
          className="font-ui text-[11px] uppercase tracking-[0.1em] text-[var(--stud-b)] hover:underline"
        >
          Start a run →
        </a>
      </div>
    );
  }

  // Newest-first display. Backend returns in rpush order, so reverse for newest-first.
  const ordered = [...runs].reverse();

  return (
    <ul className="divide-y divide-[var(--color-border)] rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
      {ordered.map((run) => (
        <li key={run.run_id}>
          <a
            href={linkFor(run)}
            className="flex items-center justify-between gap-4 px-5 py-3 transition-colors hover:bg-[var(--color-bg)]/50"
          >
            <div className="flex items-center gap-3 min-w-0">
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: statusColor(run.status) }}
                aria-label={run.status}
              />
              <span className="font-mono text-sm text-[var(--color-text)] truncate">
                {run.run_id}
              </span>
            </div>
            <div className="flex items-center gap-4 shrink-0">
              {run.current_stage && run.status === "running" && (
                <span className="font-mono text-[10px] text-[var(--color-text-muted)]">
                  at {run.current_stage}
                </span>
              )}
              <span
                className="font-ui text-[10px] uppercase tracking-[0.14em]"
                style={{ color: statusColor(run.status) }}
              >
                {run.status}
              </span>
            </div>
          </a>
        </li>
      ))}
    </ul>
  );
}
