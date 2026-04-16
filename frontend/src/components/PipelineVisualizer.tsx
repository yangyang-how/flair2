/**
 * Pipeline Visualizer — SSE-connected React island.
 *
 * Renders the 7-stage pipeline as connected nodes:
 *   Discover → Aggregate → Generate → Vote → Rank → Personalize → Done
 *
 * Derives all state from the useSSE event stream.
 * Framer Motion animates stage transitions, progress fills, and checkmarks.
 *
 * Issue: https://github.com/yangyang-how/flair2/issues/36
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { useSSE, type SSEEvent } from "../lib/sse-client";
import { Badge, ProgressBar } from "./ui";

// ── Stage definitions ─────────────────────────────────────

interface StageInfo {
  id: string;
  label: string;
  description: string;
  color: string;      // CSS variable for this stage's section
  colorDark: string;
}

const STAGES: StageInfo[] = [
  { id: "S1_MAP", label: "Discover", description: "Analyzing viral videos", color: "var(--disc-a)", colorDark: "var(--disc-b)" },
  { id: "S2_REDUCE", label: "Aggregate", description: "Extracting patterns", color: "var(--disc-a)", colorDark: "var(--disc-b)" },
  { id: "S3_SEQUENTIAL", label: "Generate", description: "Writing scripts", color: "var(--stud-a)", colorDark: "var(--stud-b)" },
  { id: "S4_MAP", label: "Vote", description: "100 personas voting", color: "var(--eval-a)", colorDark: "var(--eval-b)" },
  { id: "S5_REDUCE", label: "Rank", description: "Tallying results", color: "var(--eval-a)", colorDark: "var(--eval-b)" },
  { id: "S6_PERSONALIZE", label: "Personalize", description: "Adapting to your voice", color: "var(--pers-a)", colorDark: "var(--pers-b)" },
];

type StageStatus = "pending" | "running" | "completed" | "failed";

interface StageState {
  status: StageStatus;
  progress: number; // 0-100
  detail: string;   // e.g. "42/100 videos"
}

function initialStageStates(): Record<string, StageState> {
  const states: Record<string, StageState> = {};
  for (const stage of STAGES) {
    states[stage.id] = { status: "pending", progress: 0, detail: "" };
  }
  return states;
}

// ── Derive stage states from SSE events ───────────────────

function deriveStageStates(events: SSEEvent[]): {
  stages: Record<string, StageState>;
  pipelineDone: boolean;
  pipelineError: string | null;
  runId: string | null;
} {
  const stages = initialStageStates();
  let pipelineDone = false;
  let pipelineError: string | null = null;
  let runId: string | null = null;

  for (const evt of events) {
    const d = evt.data as Record<string, unknown>;

    switch (evt.event) {
      case "pipeline_started":
        runId = (d.run_id as string) || null;
        break;

      case "stage_started": {
        const stageId = d.stage as string;
        if (stages[stageId]) {
          stages[stageId] = {
            status: "running",
            progress: 0,
            detail: d.total_items ? `0/${d.total_items}` : "",
          };
        }
        break;
      }

      case "s1_progress": {
        const completed = d.completed as number;
        const total = d.total as number;
        stages.S1_MAP = {
          status: "running",
          progress: total > 0 ? (completed / total) * 100 : 0,
          detail: `${completed}/${total} videos`,
        };
        break;
      }

      case "s2_complete":
        stages.S2_REDUCE = {
          status: "completed",
          progress: 100,
          detail: `${d.pattern_count ?? ""} patterns`,
        };
        break;

      case "s3_progress": {
        const completed = d.completed as number;
        const total = d.total as number;
        stages.S3_SEQUENTIAL = {
          status: "running",
          progress: total > 0 ? (completed / total) * 100 : 0,
          detail: `${completed}/${total} scripts`,
        };
        break;
      }

      case "s3_complete":
        stages.S3_SEQUENTIAL = {
          status: "completed",
          progress: 100,
          detail: `${d.script_count ?? ""} scripts`,
        };
        break;

      case "vote_cast": {
        const completed = d.completed as number;
        const total = d.total as number;
        stages.S4_MAP = {
          status: "running",
          progress: total > 0 ? (completed / total) * 100 : 0,
          detail: `${completed}/${total} votes`,
        };
        break;
      }

      case "s5_complete":
        stages.S5_REDUCE = {
          status: "completed",
          progress: 100,
          detail: `Top ${d.top_n ?? ""}`,
        };
        break;

      case "s6_progress": {
        const completed = d.completed as number;
        const total = d.total as number;
        stages.S6_PERSONALIZE = {
          status: "running",
          progress: total > 0 ? (completed / total) * 100 : 0,
          detail: `${completed}/${total} scripts`,
        };
        break;
      }

      case "pipeline_complete":
        pipelineDone = true;
        // Mark all stages as completed
        for (const s of STAGES) {
          stages[s.id] = { status: "completed", progress: 100, detail: stages[s.id].detail };
        }
        break;

      case "pipeline_error":
        pipelineError = (d.error as string) || "Pipeline failed";
        // Mark current running stage as failed
        for (const s of STAGES) {
          if (stages[s.id].status === "running") {
            stages[s.id] = { ...stages[s.id], status: "failed" };
          }
        }
        break;
    }
  }

  return { stages, pipelineDone, pipelineError, runId };
}

// ── Component ─────────────────────────────────────────────

interface PipelineVisualizerProps {
  runId: string;
}

const STALL_TIMEOUT_MS = 30_000;

export default function PipelineVisualizer({ runId }: PipelineVisualizerProps) {
  const { events, connected, error } = useSSE(runId);
  const [redirecting, setRedirecting] = useState(false);
  const [stalled, setStalled] = useState(false);

  const { stages, pipelineDone, pipelineError } = useMemo(
    () => deriveStageStates(events),
    [events],
  );

  // Stall detection: warn if no events arrive for 30s while connected
  useEffect(() => {
    if (!connected || pipelineDone || pipelineError) {
      setStalled(false);
      return;
    }
    setStalled(false);
    const timer = setTimeout(() => setStalled(true), STALL_TIMEOUT_MS);
    return () => clearTimeout(timer);
  }, [events.length, connected, pipelineDone, pipelineError]);

  // Auto-redirect to vote page on completion
  useEffect(() => {
    if (pipelineDone && !redirecting) {
      setRedirecting(true);
      const timer = setTimeout(() => {
        window.location.href = `/vote/?id=${runId}`;
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [pipelineDone, runId, redirecting]);

  return (
    <div className="space-y-6">
      {/* Connection status */}
      <div className="flex items-center justify-between">
        <h2 className="font-display text-[28px] tracking-[0.08em]">Pipeline Progress</h2>
        <div className="flex items-center gap-2">
          <span
            className={`h-1.5 w-1.5 rounded-full ${
              stalled ? "bg-[var(--color-warning, #f59e0b)]" : connected ? "bg-[var(--stud-a)]" : "bg-[var(--eval-a)]"
            }`}
            style={connected && !stalled ? { animation: "dotPulse 1.5s ease-in-out infinite" } : undefined}
          />
          <span className="font-ui text-[10px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
            {stalled ? "Stalled" : connected ? "Live" : error || "Disconnected"}
          </span>
        </div>
      </div>

      {/* Stage nodes */}
      <div className="space-y-3">
        {STAGES.map((stage, i) => {
          const state = stages[stage.id];
          return (
            <StageNode
              key={stage.id}
              stage={stage}
              state={state}
              isLast={i === STAGES.length - 1}
            />
          );
        })}

        {/* Done node */}
        <motion.div
          initial={{ opacity: 0.3 }}
          animate={{ opacity: pipelineDone ? 1 : 0.3 }}
          className="flex items-center gap-3 pl-2"
        >
          <div
            className={`flex h-8 w-8 items-center justify-center rounded-full border-2 ${
              pipelineDone
                ? "border-[var(--color-success)] bg-[var(--color-success)]/10"
                : "border-[var(--color-border)]"
            }`}
          >
            {pipelineDone && (
              <motion.svg
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                className="h-4 w-4 text-[var(--color-success)]"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                  clipRule="evenodd"
                />
              </motion.svg>
            )}
          </div>
          <span className={`font-medium ${pipelineDone ? "text-[var(--color-success)]" : "text-[var(--color-text-muted)]"}`}>
            Done
          </span>
        </motion.div>
      </div>

      {/* Stall warning */}
      <AnimatePresence>
        {stalled && !pipelineError && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="rounded-lg border border-[var(--color-warning, #f59e0b)]/30 bg-[var(--color-warning, #f59e0b)]/5 p-4"
          >
            <p className="text-sm font-medium text-[var(--color-warning, #f59e0b)]">
              Pipeline appears stalled
            </p>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              No progress events received for 30 seconds. Workers may be failing silently — check CloudWatch logs.
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Error banner */}
      <AnimatePresence>
        {pipelineError && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 p-4"
          >
            <p className="text-sm font-medium text-[var(--color-error)]">
              Pipeline Error
            </p>
            <p className="mt-1 text-sm text-[var(--color-text-muted)]">
              {pipelineError}
            </p>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Redirect notice */}
      <AnimatePresence>
        {pipelineDone && (
          <motion.div
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="rounded-lg border border-[var(--color-success)]/30 bg-[var(--color-success)]/5 p-4 text-center"
          >
            <p className="text-sm text-[var(--color-success)]">
              Pipeline complete — redirecting to voting results...
            </p>
            <a
              href={`/vote/?id=${runId}`}
              className="mt-2 inline-block text-sm text-[var(--color-accent)] hover:underline"
            >
              Go now
            </a>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Activity log — collapsible */}
      <ActivityLog events={events} />
    </div>
  );
}

// ── Activity Log ─────────────────────────────────────────

function formatEventLabel(evt: SSEEvent): { label: string; detail: string; color: string } {
  const d = evt.data as Record<string, unknown>;
  switch (evt.event) {
    case "pipeline_started":
      return { label: "Pipeline started", detail: `${d.total_videos} videos, ${d.total_personas} personas, top ${d.top_n}`, color: "var(--stud-a)" };
    case "stage_started":
      return { label: `${d.stage} started`, detail: d.total_items ? `${d.total_items} items` : "", color: "var(--color-accent)" };
    case "s1_progress":
      return { label: `S1 Analyze`, detail: `video ${d.video_id} (${d.completed}/${d.total})`, color: "var(--disc-a)" };
    case "s2_complete":
      return { label: "S2 Aggregate complete", detail: `${d.pattern_count} patterns`, color: "var(--disc-a)" };
    case "s3_progress":
      return { label: "S3 Generate", detail: `${d.completed}/${d.total} scripts`, color: "var(--stud-a)" };
    case "s3_complete":
      return { label: "S3 Generate complete", detail: `${d.script_count} scripts`, color: "var(--stud-a)" };
    case "vote_cast":
      return { label: `S4 Vote`, detail: `${d.persona_id} voted (${d.completed}/${d.total})`, color: "var(--eval-a)" };
    case "s5_complete":
      return { label: "S5 Rank complete", detail: `top ${d.top_n}`, color: "var(--eval-a)" };
    case "s6_progress":
      return { label: "S6 Personalize", detail: `${d.script_id} (${d.completed}/${d.total})`, color: "var(--pers-a)" };
    case "pipeline_complete":
      return { label: "Pipeline complete", detail: `${d.result_count ?? ""} results`, color: "var(--color-success)" };
    case "pipeline_error":
      return { label: "Pipeline error", detail: (d.error as string) || "Unknown error", color: "var(--color-error)" };
    case "pipeline_recovered":
      return { label: "Pipeline recovered", detail: `from S4 checkpoint ${d.s4_checkpoint}, ${d.remaining_personas} remaining`, color: "var(--color-warning, #f59e0b)" };
    default:
      return { label: evt.event, detail: JSON.stringify(d), color: "var(--color-text-muted)" };
  }
}

function ActivityLog({ events }: { events: SSEEvent[] }) {
  const [open, setOpen] = useState(false);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [events.length, open]);

  return (
    <div className="rounded-lg border border-[var(--color-border)] overflow-hidden">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between p-3 text-left hover:bg-[var(--color-surface)] transition-colors"
      >
        <div className="flex items-center gap-2">
          <svg
            className={`h-3 w-3 text-[var(--color-text-muted)] transition-transform ${open ? "rotate-90" : ""}`}
            viewBox="0 0 12 12"
            fill="currentColor"
          >
            <path d="M4.5 2l5 4-5 4V2z" />
          </svg>
          <span className="font-ui text-[11px] uppercase tracking-[0.1em] text-[var(--color-text-muted)]">
            Activity Log
          </span>
          <span className="font-ui text-[10px] text-[var(--color-text-muted)] opacity-60">
            {events.length} events
          </span>
        </div>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0 }}
            animate={{ height: "auto" }}
            exit={{ height: 0 }}
            className="overflow-hidden"
          >
            <div className="max-h-64 overflow-y-auto border-t border-[var(--color-border)] bg-[var(--color-bg, #000)]/30">
              {events.length === 0 ? (
                <p className="p-3 text-xs text-[var(--color-text-muted)]">
                  Waiting for events...
                </p>
              ) : (
                <div className="divide-y divide-[var(--color-border)]/50">
                  {events.map((evt, i) => {
                    const { label, detail, color } = formatEventLabel(evt);
                    const time = evt.timestamp
                      ? new Date(evt.timestamp).toLocaleTimeString()
                      : "";
                    return (
                      <div key={evt.id || i} className="flex items-start gap-2 px-3 py-1.5 font-mono text-[11px]">
                        <span className="shrink-0 text-[var(--color-text-muted)] opacity-50 w-16">
                          {time}
                        </span>
                        <span className="shrink-0" style={{ color }}>
                          {label}
                        </span>
                        {detail && (
                          <span className="text-[var(--color-text-muted)] truncate">
                            {detail}
                          </span>
                        )}
                      </div>
                    );
                  })}
                  <div ref={logEndRef} />
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Stage Node ────────────────────────────────────────────

function StageNode({
  stage,
  state,
  isLast,
}: {
  stage: StageInfo;
  state: StageState;
  isLast: boolean;
}) {
  const badgeStatus = state.status;

  return (
    <div className="relative">
      {/* Connector line */}
      {!isLast && (
        <div className="absolute left-[19px] top-10 h-[calc(100%)] w-px bg-[var(--color-border)]" />
      )}

      <motion.div
        layout
        className={`flex items-start gap-3 rounded-lg p-2 transition-colors ${
          state.status === "running" ? "bg-[var(--color-surface)]" : ""
        }`}
      >
        {/* Circle indicator */}
        <div className="relative z-10 mt-0.5">
          <motion.div
            className={`flex h-8 w-8 items-center justify-center rounded-full border-2 transition-colors ${
              state.status === "completed"
                ? "border-[var(--color-success)] bg-[var(--color-success)]/10"
                : state.status === "running"
                  ? "border-[var(--color-accent)] bg-[var(--color-accent)]/10"
                  : state.status === "failed"
                    ? "border-[var(--color-error)] bg-[var(--color-error)]/10"
                    : "border-[var(--color-border)] bg-transparent"
            }`}
          >
            {state.status === "completed" && (
              <motion.svg
                initial={{ scale: 0 }}
                animate={{ scale: 1 }}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
                className="h-4 w-4 text-[var(--color-success)]"
                viewBox="0 0 20 20"
                fill="currentColor"
              >
                <path
                  fillRule="evenodd"
                  d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                  clipRule="evenodd"
                />
              </motion.svg>
            )}
            {state.status === "running" && (
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-[var(--color-accent)]" />
            )}
            {state.status === "failed" && (
              <svg className="h-4 w-4 text-[var(--color-error)]" viewBox="0 0 20 20" fill="currentColor">
                <path
                  fillRule="evenodd"
                  d="M4.293 4.293a1 1 0 011.414 0L10 8.586l4.293-4.293a1 1 0 111.414 1.414L11.414 10l4.293 4.293a1 1 0 01-1.414 1.414L10 11.414l-4.293 4.293a1 1 0 01-1.414-1.414L8.586 10 4.293 5.707a1 1 0 010-1.414z"
                  clipRule="evenodd"
                />
              </svg>
            )}
          </motion.div>
        </div>

        {/* Content */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium">{stage.label}</span>
            <Badge status={badgeStatus} className="text-[10px]" />
          </div>
          <p className="mt-0.5 text-xs text-[var(--color-text-muted)]">
            {state.detail || stage.description}
          </p>

          {/* Progress bar for running stages with fan-out */}
          <AnimatePresence>
            {state.status === "running" && state.progress > 0 && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                className="mt-2"
              >
                <ProgressBar value={state.progress} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}
