/**
 * Shared select/dropdown component.
 */

import type { SelectHTMLAttributes } from "react";

interface Option {
  value: string;
  label: string;
}

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: Option[];
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
    <div className="space-y-1.5">
      {label && (
        <label
          htmlFor={selectId}
          className="block text-sm font-medium text-[var(--color-text)]"
        >
          {label}
        </label>
      )}
      <select
        id={selectId}
        className={`w-full rounded-lg border bg-[var(--color-bg)] px-3 py-2 text-sm text-[var(--color-text)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] ${
          error
            ? "border-[var(--color-error)]"
            : "border-[var(--color-border)]"
        } ${className}`}
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
        <p className="text-xs text-[var(--color-error)]">{error}</p>
      )}
    </div>
  );
}
