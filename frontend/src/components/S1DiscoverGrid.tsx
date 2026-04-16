/**
 * S1 Discover Grid — 10x10 grid of video cards showing concurrent analysis.
 *
 * Each card transitions: pending → processing → completed
 * Colors encode the extracted hook type. The concurrency meter shows
 * how many workers are active simultaneously.
 */

import { useMemo } from "react";
import { motion } from "framer-motion";
import type { SSEEvent } from "../lib/sse-client";

const HOOK_COLORS: Record<string, string> = {
  question: "#3b82f6",
  story: "#f59e0b",
  shock: "#ef4444",
  challenge: "#22c55e",
  reveal: "#a855f7",
  tutorial: "#06b6d4",
  relatable: "#ec4899",
  confession: "#f97316",
  "myth-busting": "#14b8a6",
  transformation: "#8b5cf6",
};

function getHookColor(hookType: string): string {
  const key = hookType.toLowerCase().replace(/[_\s]+/g, "-");
  for (const [pattern, color] of Object.entries(HOOK_COLORS)) {
    if (key.includes(pattern)) return color;
  }
  return "#6b7280";
}

type CardState = "pending" | "processing" | "completed";

interface VideoCardData {
  videoId: string;
  index: number;
  state: CardState;
  description?: string;
  hookType?: string;
  pacing?: string;
  triggerCount?: number;
}

function deriveVideoStates(events: SSEEvent[], totalVideos: number): VideoCardData[] {
  const cards: Map<string, VideoCardData> = new Map();
  const videoOrder: string[] = [];

  for (const evt of events) {
    const d = evt.data as Record<string, unknown>;

    if (evt.event === "s1_task_started") {
      const vid = d.video_id as string;
      if (!cards.has(vid)) {
        videoOrder.push(vid);
      }
      cards.set(vid, {
        videoId: vid,
        index: videoOrder.indexOf(vid),
        state: "processing",
        description: (d.description as string) || undefined,
      });
    }

    if (evt.event === "s1_progress") {
      const vid = d.video_id as string;
      if (!cards.has(vid)) {
        videoOrder.push(vid);
      }
      const existing = cards.get(vid);
      cards.set(vid, {
        videoId: vid,
        index: videoOrder.indexOf(vid),
        state: "completed",
        description: existing?.description,
        hookType: (d.hook_type as string) || undefined,
        pacing: (d.pacing as string) || undefined,
        triggerCount: (d.trigger_count as number) || undefined,
      });
    }
  }

  const result: VideoCardData[] = [];
  for (let i = 0; i < totalVideos; i++) {
    if (i < videoOrder.length) {
      result.push(cards.get(videoOrder[i])!);
    } else {
      result.push({
        videoId: `pending_${i}`,
        index: i,
        state: "pending",
      });
    }
  }
  return result;
}

function VideoCard({ card }: { card: VideoCardData }) {
  const hookColor = card.hookType ? getHookColor(card.hookType) : undefined;

  if (card.state === "pending") {
    return (
      <div className="aspect-square rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]/50 flex items-center justify-center">
        <span className="text-[9px] text-[var(--color-text-muted)] opacity-30 font-mono">
          {card.index + 1}
        </span>
      </div>
    );
  }

  if (card.state === "processing") {
    return (
      <motion.div
        initial={{ opacity: 0.5 }}
        animate={{ opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
        className="aspect-square rounded-md border-2 border-[var(--disc-a)] bg-[var(--disc-a)]/10 flex flex-col items-center justify-center p-0.5 overflow-hidden"
      >
        <span className="text-[8px] font-mono text-[var(--disc-a)] font-medium">
          {card.index + 1}
        </span>
        {card.description && (
          <span className="text-[6px] text-[var(--color-text-muted)] text-center leading-tight mt-0.5 line-clamp-2">
            {card.description}
          </span>
        )}
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className="aspect-square rounded-md flex flex-col items-center justify-center p-0.5 overflow-hidden cursor-default"
      style={{
        backgroundColor: hookColor ? `${hookColor}20` : "var(--color-surface)",
        borderWidth: 2,
        borderColor: hookColor || "var(--color-success)",
        borderStyle: "solid",
      }}
      title={`${card.videoId}\n${card.hookType || ""} / ${card.pacing || ""}\n${card.triggerCount ?? 0} triggers`}
    >
      <svg className="h-2.5 w-2.5 mb-0.5" viewBox="0 0 20 20" fill={hookColor || "var(--color-success)"}>
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
      </svg>
      {card.hookType && (
        <span className="text-[7px] font-mono font-medium text-center leading-tight" style={{ color: hookColor }}>
          {card.hookType.length > 10 ? card.hookType.slice(0, 9) + "..." : card.hookType}
        </span>
      )}
      {card.pacing && (
        <span className="text-[6px] text-[var(--color-text-muted)]">{card.pacing}</span>
      )}
    </motion.div>
  );
}

function PatternSummary({ cards }: { cards: VideoCardData[] }) {
  const completed = cards.filter((c) => c.state === "completed");
  if (completed.length === 0) return null;

  const counts: Record<string, number> = {};
  for (const c of completed) {
    const hook = c.hookType || "unknown";
    counts[hook] = (counts[hook] || 0) + 1;
  }

  const sorted = Object.entries(counts).sort((a, b) => b[1] - a[1]);

  return (
    <div className="flex flex-wrap gap-2">
      {sorted.map(([hook, count]) => (
        <span
          key={hook}
          className="inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-mono"
          style={{
            backgroundColor: `${getHookColor(hook)}15`,
            color: getHookColor(hook),
            border: `1px solid ${getHookColor(hook)}30`,
          }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: getHookColor(hook) }} />
          {hook} ({count})
        </span>
      ))}
    </div>
  );
}

interface S1DiscoverGridProps {
  events: SSEEvent[];
  totalVideos: number;
}

export default function S1DiscoverGrid({ events, totalVideos }: S1DiscoverGridProps) {
  const cards = useMemo(() => deriveVideoStates(events, totalVideos), [events, totalVideos]);

  const processing = cards.filter((c) => c.state === "processing").length;
  const completed = cards.filter((c) => c.state === "completed").length;

  return (
    <div className="space-y-3">
      {/* Header with concurrency meter */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-ui text-[11px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
            Analyzing {totalVideos} videos
          </span>
          <span className="font-mono text-[11px] text-[var(--color-text)]">
            {completed}/{totalVideos}
          </span>
        </div>
        {processing > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-1.5"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--disc-a)] animate-pulse" />
            <span className="font-mono text-[10px] text-[var(--disc-a)]">
              {processing} concurrent
            </span>
          </motion.div>
        )}
      </div>

      {/* 10x10 Grid */}
      <div className="grid grid-cols-10 gap-1">
        {cards.map((card) => (
          <VideoCard key={card.videoId} card={card} />
        ))}
      </div>

      {/* Pattern summary */}
      <PatternSummary cards={cards} />
    </div>
  );
}
