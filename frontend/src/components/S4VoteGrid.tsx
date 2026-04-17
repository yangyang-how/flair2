/**
 * S4 Vote Grid — tiles of voting personas showing concurrent evaluation.
 *
 * Each tile transitions: pending → voting → voted
 * Mirrors the S1 Discover grid: pulse while in-flight, checkmark on completion.
 */

import { useMemo } from "react";
import { motion } from "framer-motion";
import type { SSEEvent } from "../lib/sse-client";

type CardState = "pending" | "voting" | "voted";

interface PersonaCardData {
  personaId: string;
  index: number;
  state: CardState;
  name?: string;
  location?: string;
}

function derivePersonaStates(events: SSEEvent[], totalPersonas: number): PersonaCardData[] {
  const cards: Map<string, PersonaCardData> = new Map();
  const personaOrder: string[] = [];

  for (const evt of events) {
    const d = evt.data as Record<string, unknown>;

    if (evt.event === "s4_task_started") {
      const pid = d.persona_id as string;
      if (!cards.has(pid)) personaOrder.push(pid);
      cards.set(pid, {
        personaId: pid,
        index: personaOrder.indexOf(pid),
        state: "voting",
        name: (d.name as string) || undefined,
        location: (d.location as string) || undefined,
      });
    }

    if (evt.event === "vote_cast") {
      const pid = d.persona_id as string;
      if (!cards.has(pid)) personaOrder.push(pid);
      const existing = cards.get(pid);
      cards.set(pid, {
        personaId: pid,
        index: personaOrder.indexOf(pid),
        state: "voted",
        name: (d.persona_name as string) || existing?.name,
        location: existing?.location,
      });
    }
  }

  const result: PersonaCardData[] = [];
  for (let i = 0; i < totalPersonas; i++) {
    if (i < personaOrder.length) {
      result.push(cards.get(personaOrder[i])!);
    } else {
      result.push({
        personaId: `pending_${i}`,
        index: i,
        state: "pending",
      });
    }
  }
  return result;
}

function displayName(name: string | undefined, personaId: string): string {
  if (!name || name === personaId) return personaId.replace("persona_", "#");
  const parts = name.split(" ");
  return parts[0].length <= 10 ? parts[0] : parts[0].slice(0, 9) + "…";
}

function PersonaCard({ card }: { card: PersonaCardData }) {
  if (card.state === "pending") {
    return (
      <div className="aspect-square rounded-md border border-[var(--color-border)] bg-[var(--color-bg)]/50 flex items-center justify-center">
        <span className="text-[9px] text-[var(--color-text-muted)] opacity-30 font-mono">
          {card.index + 1}
        </span>
      </div>
    );
  }

  if (card.state === "voting") {
    return (
      <motion.div
        initial={{ opacity: 0.5 }}
        animate={{ opacity: [0.5, 1, 0.5] }}
        transition={{ duration: 1.5, repeat: Infinity, ease: "easeInOut" }}
        className="aspect-square rounded-md border-2 border-[var(--eval-a)] bg-[var(--eval-a)]/10 flex flex-col items-center justify-center p-0.5 overflow-hidden"
      >
        <span className="text-[8px] font-mono text-[var(--eval-a)] font-medium">
          {displayName(card.name, card.personaId)}
        </span>
        {card.location && (
          <span className="text-[6px] text-[var(--color-text-muted)] text-center leading-tight mt-0.5 line-clamp-1">
            {card.location.split(",")[0]}
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
      className="aspect-square rounded-md flex flex-col items-center justify-center p-0.5 overflow-hidden cursor-default border-2 border-[var(--color-success)] bg-[var(--color-success)]/10"
      title={`${card.name || card.personaId}${card.location ? ` — ${card.location}` : ""}`}
    >
      <svg
        className="h-2.5 w-2.5 mb-0.5"
        viewBox="0 0 20 20"
        fill="var(--color-success)"
      >
        <path
          fillRule="evenodd"
          d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
          clipRule="evenodd"
        />
      </svg>
      <span className="text-[7px] font-mono font-medium text-center leading-tight text-[var(--color-text)]">
        {displayName(card.name, card.personaId)}
      </span>
    </motion.div>
  );
}

interface S4VoteGridProps {
  events: SSEEvent[];
  totalPersonas: number;
}

export default function S4VoteGrid({ events, totalPersonas }: S4VoteGridProps) {
  const cards = useMemo(
    () => derivePersonaStates(events, totalPersonas),
    [events, totalPersonas],
  );

  const voting = cards.filter((c) => c.state === "voting").length;
  const voted = cards.filter((c) => c.state === "voted").length;

  // 42 → 7 cols × 6 rows. For other sizes, pick a square-ish column count.
  const cols = totalPersonas <= 16 ? 4 : totalPersonas <= 42 ? 7 : 10;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="font-ui text-[11px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
            {totalPersonas} personas voting
          </span>
          <span className="font-mono text-[11px] text-[var(--color-text)]">
            {voted}/{totalPersonas}
          </span>
        </div>
        {voting > 0 && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex items-center gap-1.5"
          >
            <span className="h-1.5 w-1.5 rounded-full bg-[var(--eval-a)] animate-pulse" />
            <span className="font-mono text-[10px] text-[var(--eval-a)]">
              {voting} concurrent
            </span>
          </motion.div>
        )}
      </div>

      <div
        className="grid gap-1"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
      >
        {cards.map((card) => (
          <PersonaCard key={card.personaId} card={card} />
        ))}
      </div>
    </div>
  );
}
