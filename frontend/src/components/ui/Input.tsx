/**
 * Text input — V1 design language.
 * Semi-transparent white, subtle border, DM Sans.
 */

import type { InputHTMLAttributes } from "react";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helper?: string;
}

export default function Input({
  label,
  error,
  helper,
  id,
  className = "",
  ...props
}: InputProps) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className={`space-y-1 ${className}`}>
      {label && (
        <label
          htmlFor={inputId}
          className="block font-ui text-[10px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full rounded-md border bg-[rgba(255,255,255,0.6)] px-4 py-3 font-ui text-sm font-light transition-colors placeholder:text-[var(--color-text-light)] focus:outline-none ${
          error
            ? "border-[var(--eval-a)] focus:border-[var(--eval-b)]"
            : "border-[var(--color-border)] focus:border-[var(--stud-a)]"
        }`}
        {...props}
      />
      {error && (
        <p className="font-ui text-[10px] text-[var(--eval-a)]">{error}</p>
      )}
      {helper && !error && (
        <p className="font-ui text-[10px] text-[var(--color-text-light)]">{helper}</p>
      )}
    </div>
  );
}
