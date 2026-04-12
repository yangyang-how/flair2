/**
 * Button — V1 design language.
 * Rounded, uppercase, tracked letter-spacing.
 */

import type { ButtonHTMLAttributes } from "react";

const variants = {
  primary:
    "bg-[var(--stud-b)] text-white hover:bg-[var(--stud-a)]",
  secondary:
    "border border-[var(--color-border)] text-[var(--color-text-muted)] hover:border-[var(--color-ink)] hover:text-[var(--color-ink)]",
  danger:
    "bg-[var(--eval-b)] text-white hover:bg-[var(--eval-a)]",
  ghost:
    "text-[var(--color-text-muted)] hover:text-[var(--color-ink)] hover:bg-[rgba(14,12,20,0.04)]",
} as const;

const sizes = {
  sm: "px-4 py-1.5 text-[10px]",
  md: "px-6 py-2.5 text-[11px]",
  lg: "px-8 py-3 text-[12px]",
} as const;

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants;
  size?: keyof typeof sizes;
  loading?: boolean;
}

export default function Button({
  variant = "primary",
  size = "md",
  loading = false,
  disabled,
  children,
  className = "",
  ...props
}: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-full font-ui font-medium uppercase tracking-[0.1em] transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]} ${className}`}
      disabled={disabled || loading}
      {...props}
    >
      {loading && <LoadingDot />}
      {children}
    </button>
  );
}

function LoadingDot() {
  return (
    <span className="h-1.5 w-1.5 rounded-full bg-current" style={{ animation: "dotPulse 0.8s ease-in-out infinite" }} />
  );
}
