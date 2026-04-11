/**
 * Voting Animation — 100-avatar React island with live SSE voting.
 *
 * Displays a 10x10 grid of persona avatars. As vote_cast events arrive,
 * the corresponding avatar animates and the leaderboard updates.
 *
 * Can show either the live voting (SSE connected) or the final results
 * (loaded from API after pipeline completes).
 *
 * Issue: https://github.com/yangyang-how/flair2/issues/37
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
        if (d.stage === "S4_MAP") {
          totalPersonas = (d.total_items as number) || totalPersonas;
        }
        break;

      case "vote_cast": {
        const personaId = d.persona_id as string;
        const top5 = (d.top_5 as string[]) || [];
        const completed = (d.completed as number) || votes.length + 1;
        const idx = completed - 1;

        if (!votedSet.has(idx)) {
          votedSet.add(idx);
          votes.push({ personaId, top5, index: idx });

          for (const scriptId of top5) {
            tally[scriptId] = (tally[scriptId] || 0) + 1;
          }
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

  // Build sorted leaderboard
  const leaderboard: LeaderboardEntry[] = Object.entries(tally)
    .map(([scriptId, voteCount]) => ({ scriptId, votes: voteCount }))
    .sort((a, b) => b.votes - a.votes)
    .slice(0, 10);

  return {
    votes,
    votedSet,
    leaderboard,
    totalPersonas,
    pipelineDone,
    topIds,
  };
}

// ── Component ─────────────────────────────────────────────

interface VotingAnimationProps {
  runId: string;
}

export default function VotingAnimation({ runId }: VotingAnimationProps) {
  const { events, connected, error } = useSSE(runId);
  const [showGrid, setShowGrid] = useState(true);

  const {
    votes,
    votedSet,
    leaderboard,
    totalPersonas,
    pipelineDone,
    topIds,
  } = useMemo(() => deriveVotingState(events), [events]);

  const voteCount = votes.length;
  const progress = totalPersonas > 0 ? (voteCount / totalPersonas) * 100 : 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold">Audience Vote</h2>
          <p className="text-sm text-[var(--color-text-muted)]">
            {pipelineDone
              ? "Voting complete — see the winners below"
              : `${voteCount}/${totalPersonas} votes cast`}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowGrid((s) => !s)}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
          >
            {showGrid ? "Hide grid" : "Show grid"}
          </button>
          <span
            className={`h-2 w-2 rounded-full ${
              connected ? "bg-[var(--color-success)]" : "bg-[var(--color-error)]"
            }`}
          />
        </div>
      </div>

      {/* Progress */}
      <ProgressBar
        value={progress}
        label={`${voteCount} of ${totalPersonas} personas`}
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* Avatar grid */}
        <AnimatePresence>
          {showGrid && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
            >
              <AvatarGrid
                total={totalPersonas}
                votedSet={votedSet}
              />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Leaderboard */}
        <div className={showGrid ? "" : "lg:col-span-2 max-w-md mx-auto w-full"}>
          <Leaderboard
            entries={leaderboard}
            topIds={topIds}
            pipelineDone={pipelineDone}
            maxVotes={totalPersonas}
          />
        </div>
      </div>

      {/* Final actions */}
      {pipelineDone && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-lg border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 p-4 text-center"
        >
          <p className="text-sm text-[var(--color-success)]">
            Voting complete — {leaderboard[0]?.scriptId || "Script"} won with{" "}
            {leaderboard[0]?.votes || 0} votes
          </p>
          <a
            href={`/results/${runId}`}
            className="mt-2 inline-block rounded-lg bg-[var(--color-accent)] px-4 py-2 text-sm font-medium text-white hover:bg-[var(--color-accent-hover)]"
          >
            View Results
          </a>
        </motion.div>
      )}

      {/* Error */}
      {error && !pipelineDone && (
        <div className="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 p-3">
          <p className="text-sm text-[var(--color-error)]">{error}</p>
        </div>
      )}
    </div>
  );
}

// ── Avatar Grid ───────────────────────────────────────────

function AvatarGrid({
  total,
  votedSet,
}: {
  total: number;
  votedSet: Set<number>;
}) {
  // Generate stable colors for each avatar
  const colors = useMemo(() => {
    const hues = Array.from({ length: total }, (_, i) => (i * 137.5) % 360);
    return hues.map((h) => `hsl(${h}, 50%, 60%)`);
  }, [total]);

  return (
    <Card padding="sm">
      <div
        className="grid gap-1"
        style={{
          gridTemplateColumns: `repeat(${Math.min(10, Math.ceil(Math.sqrt(total)))}, 1fr)`,
        }}
      >
        {Array.from({ length: total }, (_, i) => {
          const hasVoted = votedSet.has(i);
          return (
            <motion.div
              key={i}
              className="relative aspect-square rounded-md"
              style={{
                backgroundColor: hasVoted ? colors[i] : "var(--color-border)",
              }}
              animate={
                hasVoted
                  ? {
                      scale: [1, 1.2, 1],
                      opacity: 1,
                    }
                  : { scale: 1, opacity: 0.3 }
              }
              transition={{
                duration: 0.3,
                ease: "easeOut",
              }}
            >
              {hasVoted && (
                <motion.div
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="absolute inset-0 flex items-center justify-center text-[8px] font-bold text-white/80"
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
  entries,
  topIds,
  pipelineDone,
  maxVotes,
}: {
  entries: LeaderboardEntry[];
  topIds: string[];
  pipelineDone: boolean;
  maxVotes: number;
}) {
  return (
    <Card padding="sm">
      <h3 className="mb-3 text-sm font-semibold text-[var(--color-text-muted)]">
        Leaderboard
      </h3>

      {entries.length === 0 ? (
        <p className="py-4 text-center text-sm text-[var(--color-text-muted)]">
          Waiting for votes...
        </p>
      ) : (
        <div className="space-y-2">
          <AnimatePresence mode="popLayout">
            {entries.map((entry, rank) => {
              const isWinner = pipelineDone && rank === 0;
              const isFinalTop = topIds.includes(entry.scriptId);
              const barWidth = maxVotes > 0 ? (entry.votes / maxVotes) * 100 : 0;

              return (
                <motion.div
                  key={entry.scriptId}
                  layout
                  initial={{ opacity: 0, x: -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  className={`flex items-center gap-2 rounded-md p-1.5 text-sm ${
                    isWinner
                      ? "bg-[var(--color-accent)]/10 border border-[var(--color-accent)]/20"
                      : ""
                  }`}
                >
                  <span className="w-5 shrink-0 text-right text-xs font-mono text-[var(--color-text-muted)]">
                    {rank + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between">
                      <span className="truncate font-mono text-xs">
                        {entry.scriptId.slice(0, 8)}
                        {isFinalTop && pipelineDone && (
                          <span className="ml-1 text-[var(--color-success)]">*</span>
                        )}
                      </span>
                      <span className="ml-2 shrink-0 text-xs font-medium text-[var(--color-text-muted)]">
                        {entry.votes}
                      </span>
                    </div>
                    <div className="mt-1 h-1 overflow-hidden rounded-full bg-[var(--color-bg)]">
                      <motion.div
                        className="h-full rounded-full bg-[var(--color-accent)]"
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
