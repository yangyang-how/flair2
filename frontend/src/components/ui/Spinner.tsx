/**
 * Loading spinner — V1 design language.
 * Simple pulsing dot instead of spinning circle.
 */

const sizes = {
  sm: "h-2 w-2",
  md: "h-3 w-3",
  lg: "h-4 w-4",
} as const;

interface SpinnerProps {
  size?: keyof typeof sizes;
  className?: string;
}

export default function Spinner({
  size = "md",
  className = "",
}: SpinnerProps) {
  return (
    <span
      className={`inline-block rounded-full bg-[var(--stud-a)] ${sizes[size]} ${className}`}
      style={{ animation: "dotPulse 1s ease-in-out infinite" }}
    />
  );
}
