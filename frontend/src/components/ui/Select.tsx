/**
 * Select dropdown — V1 design language.
 */

import type { SelectHTMLAttributes } from "react";

interface SelectOption {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: SelectOption[];
  placeholder?: string;
}

export default function Select({
  label,
  error,
  options,
  placeholder,
  id,
  className = "",
  ...props
}: SelectProps) {
  const selectId = id || label?.toLowerCase().replace(/\s+/g, "-");

  return (
    <div className={`space-y-1 ${className}`}>
      {label && (
        <label
          htmlFor={selectId}
          className="block font-ui text-[10px] font-medium uppercase tracking-[0.1em] text-[var(--color-text-muted)]"
        >
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`w-full rounded-md border bg-[rgba(255,255,255,0.6)] px-4 py-3 font-ui text-sm font-light transition-colors focus:outline-none ${
          error
            ? "border-[var(--eval-a)] focus:border-[var(--eval-b)]"
            : "border-[var(--color-border)] focus:border-[var(--stud-a)]"
        }`}
        {...props}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>
      {error && (
        <p className="font-ui text-[10px] text-[var(--eval-a)]">{error}</p>
      )}
    </div>
  );
}
