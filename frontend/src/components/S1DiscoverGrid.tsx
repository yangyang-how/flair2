/**
 * S1 Discover Grid — 10x10 grid of video cards showing concurrent analysis.
 *
 * Each card transitions: pending → processing → completed. The grid
 * communicates progress only — extracted hook types and pacing details
 * live in the activity log instead.
 */

import { useMemo } from "react";
import { motion } from "framer-motion";
import type { SSEEvent } from "../lib/sse-client";

type CardState = "pending" | "processing" | "completed" | "skipped";

interface VideoCardData {
  videoId: string;
  index: number;
  state: CardState;
  description?: string;
  skipReason?: string;
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
      });
    }

    if (evt.event === "s1_video_skipped") {
      const vid = d.video_id as string;
      if (!cards.has(vid)) {
        videoOrder.push(vid);
      }
      const existing = cards.get(vid);
      cards.set(vid, {
        videoId: vid,
        index: videoOrder.indexOf(vid),
        state: "skipped",
        description: existing?.description,
        skipReason: (d.reason as string) || undefined,
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

  if (card.state === "skipped") {
    return (
      <motion.div
        initial={{ scale: 0.8, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        transition={{ type: "spring", stiffness: 500, damping: 30 }}
        className="aspect-square rounded-md flex items-center justify-center cursor-default border-2 border-[var(--color-error)] bg-[var(--color-error)]/10"
        title={
          card.skipReason
            ? `${card.videoId} — skipped: ${card.skipReason.slice(0, 120)}`
            : `${card.videoId} — skipped`
        }
      >
        <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="var(--color-error)">
          <path fillRule="evenodd" d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z" clipRule="evenodd" />
        </svg>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ scale: 0.8, opacity: 0 }}
      animate={{ scale: 1, opacity: 1 }}
      transition={{ type: "spring", stiffness: 500, damping: 30 }}
      className="aspect-square rounded-md flex items-center justify-center cursor-default border-2 border-[var(--color-success)] bg-[var(--color-success)]/10"
      title={card.videoId}
    >
      <svg className="h-3.5 w-3.5" viewBox="0 0 20 20" fill="var(--color-success)">
        <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
      </svg>
    </motion.div>
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
  const skipped = cards.filter((c) => c.state === "skipped").length;
  const processed = completed + skipped;

  return (
    <div className="space-y-3">
      {/* Header with concurrency meter */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-ui text-[11px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
            Analyzing {totalVideos} videos
          </span>
          <span className="font-mono text-[11px] text-[var(--color-text)]">
            {processed}/{totalVideos}
            {skipped > 0 && (
              <span className="ml-2 text-[var(--color-error)]">
                ({skipped} skipped)
              </span>
            )}
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
    </div>
  );
}
