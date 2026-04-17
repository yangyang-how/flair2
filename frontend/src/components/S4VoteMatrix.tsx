/**
 * S4 Vote Matrix — 20 scripts × 42 voters matrix showing concurrent evaluation.
 *
 * Cell states:
 *   blank  — voter hasn't started yet
 *   green  — voter picked this script (one of their top-5)
 *   grey   — voter voted but did NOT pick this script
 *
 * Bottom row: running vote count per script (0–N voters).
 */

import { useMemo } from "react";
import type { SSEEvent } from "../lib/sse-client";

interface VoterRow {
  personaId: string;
  displayName: string;
  location?: string;
  state: "pending" | "voting" | "voted";
  picks: Set<string>;
}

function firstName(name: string | undefined, personaId: string): string {
  if (!name || name === personaId) return personaId.replace("persona_", "#");
  const parts = name.split(" ");
  return parts[0].length <= 12 ? parts[0] : parts[0].slice(0, 11) + "…";
}

function deriveMatrix(
  events: SSEEvent[],
  totalPersonas: number,
): { rows: VoterRow[]; scriptIds: string[] } {
  let scriptIds: string[] = [];
  const rowsByPersona: Map<string, VoterRow> = new Map();
  const order: string[] = [];

  for (const evt of events) {
    const d = evt.data as Record<string, unknown>;

    if (evt.event === "s3_complete" && Array.isArray(d.script_ids)) {
      scriptIds = d.script_ids as string[];
    }

    if (evt.event === "s4_task_started") {
      const pid = d.persona_id as string;
      if (!rowsByPersona.has(pid)) order.push(pid);
      rowsByPersona.set(pid, {
        personaId: pid,
        displayName: firstName(d.name as string | undefined, pid),
        location: (d.location as string) || undefined,
        state: "voting",
        picks: new Set(),
      });
    }

    if (evt.event === "vote_cast") {
      const pid = d.persona_id as string;
      if (!rowsByPersona.has(pid)) order.push(pid);
      const existing = rowsByPersona.get(pid);
      const top5 = (d.top_5 as string[] | undefined) || [];
      rowsByPersona.set(pid, {
        personaId: pid,
        displayName: firstName(
          (d.persona_name as string | undefined) || existing?.displayName,
          pid,
        ),
        location: existing?.location,
        state: "voted",
        picks: new Set(top5),
      });
    }
  }

  // Reserve all 42 rows — pending rows appear blank until their voter starts.
  const rows: VoterRow[] = [];
  for (let i = 0; i < totalPersonas; i++) {
    if (i < order.length) {
      rows.push(rowsByPersona.get(order[i])!);
    } else {
      rows.push({
        personaId: `pending_${i}`,
        displayName: `${i + 1}`,
        state: "pending",
        picks: new Set(),
      });
    }
  }

  return { rows, scriptIds };
}

interface S4VoteMatrixProps {
  events: SSEEvent[];
  totalPersonas: number;
}

export default function S4VoteMatrix({ events, totalPersonas }: S4VoteMatrixProps) {
  const { rows, scriptIds } = useMemo(
    () => deriveMatrix(events, totalPersonas),
    [events, totalPersonas],
  );

  // If we don't know the script axis yet, show a placeholder.
  if (scriptIds.length === 0) {
    return (
      <div className="text-[11px] font-mono text-[var(--color-text-muted)]">
        Waiting for S3 to publish script IDs…
      </div>
    );
  }

  const columnVoteCounts: number[] = scriptIds.map((sid) =>
    rows.reduce((n, r) => n + (r.picks.has(sid) ? 1 : 0), 0),
  );
  const maxVotes = Math.max(1, ...columnVoteCounts);

  const votedRows = rows.filter((r) => r.state === "voted").length;
  const votingRows = rows.filter((r) => r.state === "voting").length;

  const CELL = 22; // px — cell width & height
  const NAME_W = 96; // px — left sidebar width

  return (
    <div className="space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-ui text-[11px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
            {totalPersonas} voters × {scriptIds.length} scripts
          </span>
          <span className="font-mono text-[11px] text-[var(--color-text)]">
            {votedRows}/{totalPersonas}
          </span>
        </div>
        {votingRows > 0 && (
          <div className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--eval-a)] animate-pulse" />
            <span className="font-mono text-[10px] text-[var(--eval-a)]">
              {votingRows} concurrent
            </span>
          </div>
        )}
      </div>

      {/* Matrix — scrolls horizontally if viewport narrower than content */}
      <div className="overflow-x-auto">
        <div className="inline-block">
          {/* Column header row: #1 … #N */}
          <div className="flex" style={{ paddingLeft: NAME_W }}>
            {scriptIds.map((sid, i) => (
              <div
                key={sid}
                className="flex items-center justify-center font-mono text-[9px] text-[var(--color-text-muted)]"
                style={{ width: CELL, height: CELL }}
                title={sid}
              >
                {i + 1}
              </div>
            ))}
          </div>

          {/* Voter rows */}
          {rows.map((row) => (
            <div key={row.personaId} className="flex">
              <div
                className="flex items-center justify-end pr-2 font-mono text-[10px] truncate"
                style={{
                  width: NAME_W,
                  height: CELL,
                  color:
                    row.state === "voting"
                      ? "var(--eval-a)"
                      : row.state === "voted"
                        ? "var(--color-text)"
                        : "var(--color-text-muted)",
                  opacity: row.state === "pending" ? 0.35 : 1,
                }}
                title={row.location ? `${row.displayName} — ${row.location}` : row.displayName}
              >
                {row.displayName}
              </div>
              {scriptIds.map((sid) => {
                const picked = row.picks.has(sid);
                let bg = "transparent";
                let border = "1px solid var(--color-border)";
                if (row.state === "voted") {
                  bg = picked ? "var(--color-success)" : "var(--color-text-muted)";
                  border = "1px solid " + (picked ? "var(--color-success)" : "var(--color-border)");
                } else if (row.state === "voting") {
                  bg = "var(--eval-a)";
                  border = "1px solid var(--eval-a)";
                }
                return (
                  <div
                    key={sid}
                    style={{
                      width: CELL,
                      height: CELL,
                      backgroundColor: bg,
                      opacity: row.state === "voted" && !picked ? 0.18 : row.state === "voting" ? 0.15 : 1,
                      borderLeft: border,
                      borderTop: border,
                    }}
                    title={`${row.displayName} → ${sid}${picked ? " (picked)" : ""}`}
                  />
                );
              })}
            </div>
          ))}

          {/* Tally row — vote count per script */}
          <div className="flex mt-1" style={{ paddingLeft: NAME_W }}>
            {scriptIds.map((sid, i) => {
              const n = columnVoteCounts[i];
              const heightPct = (n / maxVotes) * 100;
              return (
                <div
                  key={sid}
                  className="flex flex-col items-center justify-end"
                  style={{ width: CELL, height: CELL * 1.5 }}
                  title={`${sid}: ${n} votes`}
                >
                  <div
                    className="w-full"
                    style={{
                      height: `${heightPct}%`,
                      backgroundColor: "var(--eval-a)",
                      opacity: 0.7,
                    }}
                  />
                  <span className="font-mono text-[9px] text-[var(--color-text-muted)] mt-0.5">
                    {n}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
