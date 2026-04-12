/**
 * Status badge — V1 design language.
 * Uses pipeline section colors for each status.
 */

const statusStyles = {
  pending: "bg-[var(--disc-d)] text-[var(--disc-b)] border-[var(--disc-c)]",
  running: "bg-[var(--stud-d)] text-[var(--stud-b)] border-[var(--stud-c)]",
  completed: "bg-[var(--stud-d)] text-[var(--stud-b)] border-[var(--stud-c)]",
  failed: "bg-[var(--eval-d)] text-[var(--eval-b)] border-[var(--eval-c)]",
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
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-ui text-[9px] font-medium uppercase tracking-[0.1em] ${statusStyles[status]} ${className}`}
    >
      {status === "running" && (
        <span className="mr-1.5 h-1.5 w-1.5 rounded-full bg-current" style={{ animation: "dotPulse 1s ease-in-out infinite" }} />
      )}
      {label || status}
    </span>
  );
}
