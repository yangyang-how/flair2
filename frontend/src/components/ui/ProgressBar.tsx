/**
 * Progress bar — V1 design language.
 * Thin, elegant, with section color support.
 */

interface ProgressBarProps {
  value: number;
  label?: string;
  color?: string;
  className?: string;
}

export default function ProgressBar({
  value,
  label,
  color = "var(--stud-a)",
  className = "",
}: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div className={`space-y-1.5 ${className}`}>
      {label && (
        <div className="flex items-center justify-between font-ui text-[10px] tracking-[0.06em]">
          <span className="text-[var(--color-text-muted)]">{label}</span>
          <span className="font-medium text-[var(--color-text-light)]">
            {Math.round(clamped)}%
          </span>
        </div>
      )}
      <div className="h-[3px] overflow-hidden rounded-full bg-[rgba(14,12,20,0.06)]">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{ width: `${clamped}%`, backgroundColor: color }}
        />
      </div>
    </div>
  );
}
