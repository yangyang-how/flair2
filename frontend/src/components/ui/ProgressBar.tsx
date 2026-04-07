/**
 * Progress bar — used for stage progress in pipeline viz
 * and vote counting in voting animation.
 */

interface ProgressBarProps {
  value: number;      // 0-100
  label?: string;
  className?: string;
}

export default function ProgressBar({
  value,
  label,
  className = "",
}: ProgressBarProps) {
  const clamped = Math.min(100, Math.max(0, value));

  return (
    <div className={`space-y-1 ${className}`}>
      {label && (
        <div className="flex items-center justify-between text-xs">
          <span className="text-[var(--color-text-muted)]">{label}</span>
          <span className="font-mono text-[var(--color-text-muted)]">
            {Math.round(clamped)}%
          </span>
        </div>
      )}
      <div className="h-2 overflow-hidden rounded-full bg-[var(--color-bg)]">
        <div
          className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-300 ease-out"
          style={{ width: `${clamped}%` }}
        />
      </div>
    </div>
  );
}
