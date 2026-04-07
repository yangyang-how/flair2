/**
 * Status badge — used for pipeline run status, stage status, etc.
 *
 * Both tracks need this: Sam's pipeline viz shows stage badges,
 * Jess's runs page shows run status badges.
 */

const statusStyles = {
  pending: "bg-yellow-500/10 text-[var(--color-warning)] border-yellow-500/20",
  running: "bg-indigo-500/10 text-[var(--color-accent)] border-indigo-500/20",
  completed: "bg-green-500/10 text-[var(--color-success)] border-green-500/20",
  failed: "bg-red-500/10 text-[var(--color-error)] border-red-500/20",
} as const;

type Status = keyof typeof statusStyles;

interface BadgeProps {
  status: Status;
  label?: string;
  className?: string;
}

export default function Badge({
  status,
  label,
  className = "",
}: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${statusStyles[status]} ${className}`}
    >
      {status === "running" && (
        <span className="mr-1.5 h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
      )}
      {label || status}
    </span>
  );
}
