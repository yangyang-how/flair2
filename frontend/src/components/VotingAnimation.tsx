/**
 * Voting Animation — 100-persona evaluation visualization.
 *
 * V2's unique feature: AI personas evaluate candidate scripts.
 * Uses the Evaluate section color palette (rose/pink).
 *
 * Design: V1 aesthetic with 10x10 persona grid and live leaderboard.
 */

import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useSSE, type SSEEvent } from "../lib/sse-client";
import { Card, ProgressBar } from "./ui";

// ── Types ─────────────────────────────────────────────────

interface Vote {
  personaId: string;
  top5: string[];
  index: number;
}

interface LeaderboardEntry {
  scriptId: string;
  votes: number;
}

// ── Derive voting state from SSE events ───────────────────

function deriveVotingState(events: SSEEvent[]) {
  const votes: Vote[] = [];
  const votedSet = new Set<number>();
  const tally: Record<string, number> = {};
  let totalPersonas = 100;
  let pipelineDone = false;
  let topIds: string[] = [];

  for (const evt of events) {
    const d = evt.data as Record<string, unknown>;
    switch (evt.event) {
      case "pipeline_started":
        totalPersonas = (d.total_personas as number) || 100;
        break;
      case "stage_started":
        if (d.stage === "S4_MAP") totalPersonas = (d.total_items as number) || totalPersonas;
        break;
      case "vote_cast": {
        const personaId = d.persona_id as string;
        const top5 = (d.top_5 as string[]) || [];
        const completed = (d.completed as number) || votes.length + 1;
        const idx = completed - 1;
        if (!votedSet.has(idx)) {
          votedSet.add(idx);
          votes.push({ personaId, top5, index: idx });
          for (const scriptId of top5) tally[scriptId] = (tally[scriptId] || 0) + 1;
        }
        break;
      }
      case "s5_complete":
        topIds = (d.top_ids as string[]) || [];
        break;
      case "pipeline_complete":
        pipelineDone = true;
        break;
    }
  }

  const leaderboard: LeaderboardEntry[] = Object.entries(tally)
    .map(([scriptId, voteCount]) => ({ scriptId, votes: voteCount }))
    .sort((a, b) => b.votes - a.votes)
    .slice(0, 10);

  return { votes, votedSet, leaderboard, totalPersonas, pipelineDone, topIds };
}

// ── Component ─────────────────────────────────────────────

interface VotingAnimationProps {
  runId: string;
}

export default function VotingAnimation({ runId }: VotingAnimationProps) {
  const { events, connected, error } = useSSE(runId);
  const [showGrid, setShowGrid] = useState(true);

  const { votedSet, leaderboard, totalPersonas, pipelineDone, topIds } =
    useMemo(() => deriveVotingState(events), [events]);

  const voteCount = votedSet.size;
  const progress = totalPersonas > 0 ? (voteCount / totalPersonas) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-[28px] tracking-[0.08em]">Audience Vote</h2>
          <p className="font-body text-base text-[var(--color-text-muted)]">
            {pipelineDone
              ? "Voting complete \u2014 see the winners below"
              : `${voteCount} of ${totalPersonas} personas have voted`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowGrid((s) => !s)}
            className="font-ui text-[10px] uppercase tracking-[0.1em] text-[var(--color-text-muted)] hover:text-[var(--color-ink)] transition-colors"
          >
            {showGrid ? "Hide grid" : "Show grid"}
          </button>
          <span
            className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-[var(--eval-a)]" : "bg-[var(--color-text-light)]"}`}
            style={connected ? { animation: "dotPulse 1.5s ease-in-out infinite" } : undefined}
          />
        </div>
      </div>

      {/* Progress */}
      <ProgressBar
        value={progress}
        label={`${voteCount} of ${totalPersonas} personas`}
        color="var(--eval-a)"
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_280px]">
        {/* Avatar grid */}
        <AnimatePresence>
          {showGrid && (
            <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
              <AvatarGrid total={totalPersonas} votedSet={votedSet} />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Leaderboard */}
        <div className={showGrid ? "" : "lg:col-span-2 max-w-md mx-auto w-full"}>
          <Leaderboard entries={leaderboard} pipelineDone={pipelineDone} maxVotes={totalPersonas} />
        </div>
      </div>

      {/* Completion */}
      {pipelineDone && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-[10px] border border-[var(--stud-c)]/40 bg-[var(--stud-d)]/30 p-6 text-center"
        >
          <p className="font-body text-base text-[var(--stud-b)]">
            Voting complete \u2014 {leaderboard[0]?.scriptId.slice(0, 8) || "Script"} won with {leaderboard[0]?.votes || 0} votes
          </p>
          <a
            href={`/results/${runId}`}
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

// ── Avatar Grid ───────────────────────────────────────────

function AvatarGrid({ total, votedSet }: { total: number; votedSet: Set<number> }) {
  // Use rose palette for voted avatars — evaluation stage color
  const colors = useMemo(() => {
    return Array.from({ length: total }, (_, i) => {
      // Spread across the eval color range: light pink → rose → deep rose
      const t = i / total;
      const hue = 340 + t * 30; // 340-370 (rose range)
      const sat = 55 + t * 20;
      const light = 65 - t * 15;
      return `hsl(${hue}, ${sat}%, ${light}%)`;
    });
  }, [total]);

  return (
    <Card padding="sm">
      <div
        className="grid gap-[3px]"
        style={{
          gridTemplateColumns: `repeat(${Math.min(10, Math.ceil(Math.sqrt(total)))}, 1fr)`,
        }}
      >
        {Array.from({ length: total }, (_, i) => {
          const hasVoted = votedSet.has(i);
          return (
            <motion.div
              key={i}
              className="relative aspect-square rounded-[4px]"
              style={{
                backgroundColor: hasVoted ? colors[i] : "rgba(14,12,20,0.04)",
              }}
              animate={
                hasVoted
                  ? { scale: [1, 1.15, 1], opacity: 1 }
                  : { scale: 1, opacity: 0.4 }
              }
              transition={{ duration: 0.3, ease: "easeOut" }}
            >
              {hasVoted && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="absolute inset-0 flex items-center justify-center font-ui text-[7px] font-medium text-white/70"
                >
                  {i + 1}
                </motion.div>
              )}
            </motion.div>
          );
        })}
      </div>
    </Card>
  );
}

// ── Leaderboard ───────────────────────────────────────────

function Leaderboard({
  entries, pipelineDone, maxVotes,
}: {
  entries: LeaderboardEntry[];
  pipelineDone: boolean;
  maxVotes: number;
}) {
  return (
    <Card padding="sm">
      <h3 className="mb-3 font-display text-sm tracking-[0.12em]">
        Leaderboard
      </h3>

      {entries.length === 0 ? (
        <p className="py-6 text-center font-body text-sm text-[var(--color-text-muted)]">
          Waiting for votes...
        </p>
      ) : (
        <div className="space-y-1.5">
          <AnimatePresence mode="popLayout">
            {entries.map((entry, rank) => {
              const isWinner = pipelineDone && rank === 0;
              const barWidth = maxVotes > 0 ? (entry.votes / maxVotes) * 100 : 0;

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
                      <span className="truncate font-ui text-[10px] tracking-[0.04em]">
                        {entry.scriptId.slice(0, 8)}
                      </span>
                      <span className="ml-2 shrink-0 font-display text-xs text-[var(--eval-b)]">
                        {entry.votes}
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
