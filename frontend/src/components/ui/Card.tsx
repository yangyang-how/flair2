/**
 * Card container — V1 design language.
 * Semi-transparent white with subtle border, rounded corners.
 */

import type { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  padding?: "sm" | "md" | "lg";
}

const paddings = {
  sm: "p-3",
  md: "p-5",
  lg: "p-7",
} as const;

export default function Card({
  children,
  className = "",
  padding = "md",
}: CardProps) {
  return (
    <div
      className={`rounded-[10px] border border-[var(--color-border)] bg-[var(--color-surface)] transition-shadow duration-200 hover:shadow-[0_6px_24px_rgba(14,12,20,0.08)] ${paddings[padding]} ${className}`}
    >
      {children}
    </div>
  );
}
