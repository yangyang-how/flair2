/**
 * Audience Vote leaderboard — live Borda-weighted ranking of candidate
 * scripts as personas vote. Companion surface to the S4 matrix on the
 * pipeline page; this view focuses on the aggregate winner.
 */

import { useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useSSE, type SSEEvent } from "../lib/sse-client";
import { Card, ProgressBar } from "./ui";

// S5 weights: rank-1 = 5pts … rank-5 = 1pt.
const BORDA_WEIGHTS = [5, 4, 3, 2, 1];
const MAX_BORDA_PER_VOTER = BORDA_WEIGHTS.reduce((a, b) => a + b, 0); // 15

interface LeaderboardEntry {
  scriptId: string;
  borda: number;
  votes: number;
}

function deriveVotingState(events: SSEEvent[]) {
  let totalPersonas = 42;
  let pipelineDone = false;
  const votedPersonas = new Set<string>();
  const bordaByScript: Record<string, number> = {};
  const votesByScript: Record<string, number> = {};

  for (const evt of events) {
    const d = evt.data as Record<string, unknown>;
    switch (evt.event) {
      case "pipeline_started":
        totalPersonas = (d.total_personas as number) || totalPersonas;
        break;
      case "stage_started":
        if (d.stage === "S4_MAP") {
          totalPersonas = (d.total_items as number) || totalPersonas;
        }
        break;
      case "vote_cast": {
        const pid = d.persona_id as string;
        if (votedPersonas.has(pid)) break;
        votedPersonas.add(pid);
        const top5 = (d.top_5 as string[]) || [];
        top5.forEach((scriptId, idx) => {
          if (idx >= BORDA_WEIGHTS.length) return;
          bordaByScript[scriptId] =
            (bordaByScript[scriptId] || 0) + BORDA_WEIGHTS[idx];
          votesByScript[scriptId] = (votesByScript[scriptId] || 0) + 1;
        });
        break;
      }
      case "pipeline_complete":
        pipelineDone = true;
        break;
    }
  }

  const leaderboard: LeaderboardEntry[] = Object.entries(bordaByScript)
    .map(([scriptId, borda]) => ({
      scriptId,
      borda,
      votes: votesByScript[scriptId] || 0,
    }))
    .sort((a, b) => b.borda - a.borda)
    .slice(0, 10);

  return { votedCount: votedPersonas.size, leaderboard, totalPersonas, pipelineDone };
}

interface VotingAnimationProps {
  runId: string;
}

export default function VotingAnimation({ runId }: VotingAnimationProps) {
  const { events, connected, error } = useSSE(runId);

  const { votedCount, leaderboard, totalPersonas, pipelineDone } = useMemo(
    () => deriveVotingState(events),
    [events],
  );

  const progress = totalPersonas > 0 ? (votedCount / totalPersonas) * 100 : 0;
  const maxPossibleBorda = totalPersonas * MAX_BORDA_PER_VOTER;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-[28px] tracking-[0.08em]">Audience Vote</h2>
          <p className="font-ui text-base text-[var(--color-text-muted)]">
            {pipelineDone
              ? "Voting complete — Borda-weighted leaderboard below"
              : `${votedCount} of ${totalPersonas} personas have voted`}
          </p>
        </div>
        <span
          className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-[var(--eval-a)]" : "bg-[var(--color-text-light)]"}`}
          style={connected ? { animation: "dotPulse 1.5s ease-in-out infinite" } : undefined}
        />
      </div>

      <ProgressBar
        value={progress}
        label={`${votedCount} of ${totalPersonas} personas`}
        color="var(--eval-a)"
      />

      <div className="max-w-2xl mx-auto w-full">
        <Leaderboard
          entries={leaderboard}
          pipelineDone={pipelineDone}
          maxBorda={maxPossibleBorda}
        />
      </div>

      {pipelineDone && leaderboard[0] && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[10px] border border-[var(--stud-c)]/40 bg-[var(--stud-d)]/30 p-6 text-center"
        >
          <p className="font-ui text-base text-[var(--stud-b)]">
            Winner — {leaderboard[0].scriptId.slice(0, 8)} with {leaderboard[0].borda} Borda pts
            <span className="text-[var(--color-text-muted)]"> ({leaderboard[0].votes} picks)</span>
          </p>
          <a
            href={`/results/?id=${runId}`}
            className="mt-3 inline-block font-ui rounded-full bg-[var(--stud-b)] px-6 py-2.5 text-[11px] font-medium uppercase tracking-[0.1em] text-white hover:bg-[var(--stud-a)] transition-colors"
          >
            View Results
          </a>
        </motion.div>
      )}

      {error && !pipelineDone && (
        <div className="rounded-[10px] border border-[var(--eval-c)] bg-[var(--eval-d)]/30 p-4">
          <p className="font-ui text-[11px] text-[var(--eval-b)]">{error}</p>
        </div>
      )}
    </div>
  );
}

function Leaderboard({
  entries,
  pipelineDone,
  maxBorda,
}: {
  entries: LeaderboardEntry[];
  pipelineDone: boolean;
  maxBorda: number;
}) {
  return (
    <Card padding="md">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className="font-display text-sm tracking-[0.12em]">Leaderboard</h3>
        <span className="font-ui text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
          Borda score · rank-weighted
        </span>
      </div>

      {entries.length === 0 ? (
        <p className="py-6 text-center font-ui text-sm text-[var(--color-text-muted)]">
          Waiting for votes…
        </p>
      ) : (
        <div className="space-y-1.5">
          <AnimatePresence mode="popLayout">
            {entries.map((entry, rank) => {
              const isWinner = pipelineDone && rank === 0;
              const barWidth = maxBorda > 0 ? (entry.borda / maxBorda) * 100 : 0;

              return (
                <motion.div
                  key={entry.scriptId}
                  layout
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`flex items-center gap-2 rounded-[6px] p-1.5 ${
                    isWinner ? "bg-[var(--eval-d)]/40 border border-[var(--eval-c)]/30" : ""
                  }`}
                >
                  <span className="w-5 shrink-0 text-right font-display text-xs text-[var(--color-text-muted)]">
                    {rank + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <span className="truncate font-mono text-[10px] tracking-[0.04em]">
                        {entry.scriptId.slice(0, 8)}
                      </span>
                      <span className="ml-2 shrink-0 font-display text-xs text-[var(--eval-b)]">
                        {entry.borda}
                        <span className="ml-1 font-ui text-[9px] text-[var(--color-text-muted)]">
                          ({entry.votes})
                        </span>
                      </span>
                    </div>
                    <div className="mt-1 h-[2px] overflow-hidden rounded-full bg-[rgba(14,12,20,0.04)]">
                      <motion.div
                        className="h-full rounded-full bg-[var(--eval-a)]"
                        initial={{ width: 0 }}
                        animate={{ width: `${barWidth}%` }}
                        transition={{ duration: 0.3 }}
                      />
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </AnimatePresence>
        </div>
      )}
    </Card>
  );
}
