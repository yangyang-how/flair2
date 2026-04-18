/**
 * S4 Vote Matrix — 20 scripts × 42 voters matrix.
 *
 * Cell states:
 *   blank  — voter hasn't started yet
 *   green gradient — voter picked this script. Darker green = higher
 *     rank (the order inside the voter's top-5 matters; see S5 scoring).
 *   grey   — voter voted but did NOT pick this script
 *
 * Bottom row: weighted Borda score per script (rank-1 = 5pts … rank-5 =
 * 1pt). Matches S5's aggregation, so the tall columns are literally the
 * scripts that are going to win.
 */

import { useMemo } from "react";
import type { SSEEvent } from "../lib/sse-client";

// S5 weights: rank-1 = 5pts through rank-5 = 1pt.
const BORDA_WEIGHTS = [5, 4, 3, 2, 1];

// 5 shades of green for rank 1 → 5. Rank-1 is the darkest; rank-5 is lightest.
// Picked by eye to stay legible on the light-lavender background.
const RANK_SHADES = [
  "#0F766E", // rank 1 — teal-700
  "#14B8A6", // rank 2 — teal-500
  "#5EEAD4", // rank 3 — teal-300
  "#99F6E4", // rank 4 — teal-200
  "#CCFBF1", // rank 5 — teal-100
];

interface VoterRow {
  personaId: string;
  displayName: string;
  location?: string;
  age?: number;
  occupation?: string;
  description?: string;
  state: "pending" | "voting" | "voted";
  /** map from script_id → rank (0-indexed, 0 = voter's #1 pick) */
  ranks: Record<string, number>;
}

function firstName(name: string | undefined, personaId: string): string {
  if (!name || name === personaId) return personaId.replace("persona_", "#");
  const parts = name.split(" ");
  return parts[0].length <= 14 ? parts[0] : parts[0].slice(0, 13) + "…";
}

function country(location?: string): string {
  if (!location) return "";
  // Entries look like "São Paulo, Brazil" — last segment is the country.
  const parts = location.split(",").map((p) => p.trim());
  return parts[parts.length - 1] || "";
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
        age: (d.age as number) || undefined,
        occupation: (d.occupation as string) || undefined,
        description: (d.description as string) || undefined,
        state: "voting",
        ranks: {},
      });
    }

    if (evt.event === "vote_cast") {
      const pid = d.persona_id as string;
      if (!rowsByPersona.has(pid)) order.push(pid);
      const existing = rowsByPersona.get(pid);
      const top5 = (d.top_5 as string[] | undefined) || [];
      const ranks: Record<string, number> = {};
      top5.forEach((sid, i) => {
        ranks[sid] = i;
      });
      rowsByPersona.set(pid, {
        personaId: pid,
        displayName: firstName(
          (d.persona_name as string | undefined) || existing?.displayName,
          pid,
        ),
        location: existing?.location,
        age: existing?.age,
        occupation: existing?.occupation,
        description:
          (d.persona_description as string | undefined) ?? existing?.description,
        state: "voted",
        ranks,
      });
    }
  }

  const rows: VoterRow[] = [];
  for (let i = 0; i < totalPersonas; i++) {
    if (i < order.length) {
      rows.push(rowsByPersona.get(order[i])!);
    } else {
      rows.push({
        personaId: `pending_${i}`,
        displayName: `${i + 1}`,
        state: "pending",
        ranks: {},
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

  if (scriptIds.length === 0) {
    return (
      <div className="text-[11px] font-mono text-[var(--color-text-muted)]">
        Waiting for S3 to publish script IDs…
      </div>
    );
  }

  // Borda totals per column (matches S5 aggregation).
  const columnBorda: number[] = scriptIds.map((sid) =>
    rows.reduce((sum, r) => {
      const rank = r.ranks[sid];
      if (rank === undefined || rank < 0 || rank >= BORDA_WEIGHTS.length) return sum;
      return sum + BORDA_WEIGHTS[rank];
    }, 0),
  );
  const columnVoteCounts: number[] = scriptIds.map((sid) =>
    rows.reduce((n, r) => n + (r.ranks[sid] !== undefined ? 1 : 0), 0),
  );
  const maxBorda = Math.max(1, ...columnBorda);

  const votedRows = rows.filter((r) => r.state === "voted").length;
  const votingRows = rows.filter((r) => r.state === "voting").length;

  const CELL = 22;
  const ROW_H = 36;  // taller than CELL so bio line fits comfortably
  const NAME_W = 260;

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

      {/* Rank legend */}
      <div className="flex items-center gap-3 text-[10px] font-mono text-[var(--color-text-muted)]">
        <span>Rank in voter's top 5:</span>
        {RANK_SHADES.map((hex, i) => (
          <span key={i} className="flex items-center gap-1">
            <span
              className="inline-block h-2.5 w-4 rounded"
              style={{ backgroundColor: hex }}
            />
            <span>#{i + 1}</span>
            <span className="text-[var(--color-text-light)]">
              ({BORDA_WEIGHTS[i]}pt)
            </span>
          </span>
        ))}
      </div>

      {/* Matrix — horizontal scroll for narrow viewports */}
      <div className="overflow-x-auto">
        <div className="inline-block">
          {/* Column headers: #1 … #N */}
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
          {rows.map((row) => {
            const subtitleParts = [
              row.age != null ? `${row.age}y` : null,
              row.occupation || null,
              country(row.location) || null,
            ].filter(Boolean);
            const tooltipParts = [
              row.displayName,
              row.location,
              row.description,
            ].filter(Boolean);
            return (
              <div key={row.personaId} className="flex items-center">
                {/* Name sidebar — name, subtitle, bio preview */}
                <div
                  className="flex flex-col justify-center pr-3 overflow-hidden"
                  style={{
                    width: NAME_W,
                    height: ROW_H,
                    opacity: row.state === "pending" ? 0.35 : 1,
                  }}
                  title={tooltipParts.join(" — ")}
                >
                  <span
                    className="font-mono text-[11px] leading-none truncate"
                    style={{
                      color:
                        row.state === "voting"
                          ? "var(--eval-a)"
                          : "var(--color-text)",
                    }}
                  >
                    {row.displayName}
                  </span>
                  {subtitleParts.length > 0 && (
                    <span className="font-ui text-[9px] leading-none text-[var(--color-text-muted)] truncate mt-0.5">
                      {subtitleParts.join(" · ")}
                    </span>
                  )}
                  {row.description && (
                    <span
                      className="font-ui text-[9px] leading-tight text-[var(--color-text-muted)] truncate mt-0.5 italic"
                      style={{ opacity: 0.75 }}
                    >
                      {row.description}
                    </span>
                  )}
                </div>
                {/* Cells */}
                {scriptIds.map((sid) => {
                  const rank = row.ranks[sid];
                  const picked = rank !== undefined;
                  let bg = "transparent";
                  if (row.state === "voted") {
                    bg = picked ? RANK_SHADES[rank] : "var(--color-text-muted)";
                  } else if (row.state === "voting") {
                    bg = "var(--eval-a)";
                  }
                  const opacity =
                    row.state === "voted" && !picked
                      ? 0.18
                      : row.state === "voting"
                        ? 0.15
                        : 1;
                  return (
                    <div
                      key={sid}
                      style={{
                        width: CELL,
                        height: CELL,
                        backgroundColor: bg,
                        opacity,
                        borderLeft: "1px solid var(--color-border)",
                        borderTop: "1px solid var(--color-border)",
                      }}
                      title={
                        picked
                          ? `${row.displayName} picked ${sid} at rank #${rank + 1} (+${BORDA_WEIGHTS[rank]}pt)`
                          : `${row.displayName} → ${sid}`
                      }
                    />
                  );
                })}
              </div>
            );
          })}

          {/* Borda tally row */}
          <div className="flex mt-1" style={{ paddingLeft: NAME_W }}>
            {scriptIds.map((sid, i) => {
              const borda = columnBorda[i];
              const votes = columnVoteCounts[i];
              const heightPct = (borda / maxBorda) * 100;
              return (
                <div
                  key={sid}
                  className="flex flex-col items-center justify-end"
                  style={{ width: CELL, height: CELL * 2 }}
                  title={`${sid}: ${borda} Borda pts (${votes} picks)`}
                >
                  <div
                    className="w-full"
                    style={{
                      height: `${heightPct}%`,
                      backgroundColor: "var(--eval-a)",
                      opacity: 0.75,
                    }}
                  />
                  <span className="font-mono text-[9px] text-[var(--color-text)] mt-0.5 font-medium">
                    {borda}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="flex" style={{ paddingLeft: NAME_W }}>
            <span
              className="font-ui text-[9px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
              style={{ width: CELL * scriptIds.length }}
            >
              Borda score (rank-weighted) · S5 uses these to pick top 10
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}
