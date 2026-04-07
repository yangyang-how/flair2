/**
 * Card container — surface-colored box with border.
 *
 * Used for: script cards (results page), run list items,
 * performance entries, dashboard panels.
 */

import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  padding?: "sm" | "md" | "lg";
}

const paddings = {
  sm: "p-3",
  md: "p-4",
  lg: "p-6",
} as const;

export default function Card({
  children,
  className = "",
  padding = "md",
}: CardProps) {
  return (
    <div
      className={`rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] ${paddings[padding]} ${className}`}
    >
      {children}
    </div>
  );
}
