/**
 * Results View — displays pipeline results with video generation.
 *
 * Loads final results from the API, shows ranked scripts in tabs,
 * and provides video generation with polling.
 *
 * Issue: https://github.com/yangyang-how/flair2/issues/38
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  type FinalResult,
  type PipelineResults,
  type VideoStatus,
  generateVideo,
  getPipelineResults,
  getVideoStatus,
} from "../lib/api-client";
import { Button, Card, Spinner, Tabs } from "./ui";

// ── Component ─────────────────────────────────────────────

interface ResultsViewProps {
  runId: string;
}

export default function ResultsView({ runId }: ResultsViewProps) {
  const [results, setResults] = useState<PipelineResults | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const data = await getPipelineResults(runId);
        if (!cancelled) {
          setResults(data);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(
            err instanceof Error ? err.message : "Failed to load results",
          );
          setLoading(false);
        }
      }
    }

    load();
    return () => {
      cancelled = true;
    };
  }, [runId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3">
        <Spinner size="lg" />
        <p className="text-sm text-[var(--color-text-muted)]">
          Loading results...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 p-6 text-center">
        <p className="font-medium text-[var(--color-error)]">
          Failed to load results
        </p>
        <p className="mt-1 text-sm text-[var(--color-text-muted)]">{error}</p>
        <a
          href={`/pipeline/${runId}`}
          className="mt-3 inline-block text-sm text-[var(--color-accent)] hover:underline"
        >
          Check pipeline status
        </a>
      </div>
    );
  }

  if (!results || results.results.length === 0) {
    return (
      <div className="py-20 text-center">
        <p className="text-[var(--color-text-muted)]">
          No results found for this run.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-semibold">Campaign Results</h2>
        <p className="text-sm text-[var(--color-text-muted)]">
          Top {results.results.length} scripts, ranked by audience vote
        </p>
      </div>

      {/* Tabs: Scripts | Video Prompts */}
      <Tabs
        tabs={[
          {
            id: "scripts",
            label: `Scripts (${results.results.length})`,
            content: (
              <ScriptList results={results.results} runId={runId} />
            ),
          },
          {
            id: "prompts",
            label: "Video Prompts",
            content: (
              <VideoPromptList results={results.results} />
            ),
          },
        ]}
      />
    </div>
  );
}

// ── Script List ───────────────────────────────────────────

function ScriptList({
  results,
  runId,
}: {
  results: FinalResult[];
  runId: string;
}) {
  return (
    <div className="space-y-4">
      {results.map((result) => (
        <ScriptCard key={result.script_id} result={result} runId={runId} />
      ))}
    </div>
  );
}

// ── Script Card ───────────────────────────────────────────

function ScriptCard({
  result,
  runId,
}: {
  result: FinalResult;
  runId: string;
}) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <div className="space-y-3">
        {/* Rank header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span
              className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ${
                result.rank === 1
                  ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                  : "bg-[var(--color-border)] text-[var(--color-text-muted)]"
              }`}
            >
              {result.rank}
            </span>
            <div>
              <span className="font-mono text-xs text-[var(--color-text-muted)]">
                {result.script_id.slice(0, 12)}
              </span>
              <div className="flex items-center gap-2">
                <span className="text-xs text-[var(--color-text-muted)]">
                  Pattern: {result.original_script.pattern_used}
                </span>
                <span className="text-xs text-[var(--color-text-muted)]">
                  Score: {result.vote_score.toFixed(1)}
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={() => setExpanded((s) => !s)}
            className="text-xs text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
        </div>

        {/* Hook (always visible) */}
        <div>
          <p className="text-xs font-semibold uppercase text-[var(--color-accent)]">
            Hook
          </p>
          <p className="mt-1 text-sm leading-relaxed">
            {result.original_script.hook}
          </p>
        </div>

        {/* Expanded content */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="space-y-3 overflow-hidden"
            >
              {/* Body */}
              <div>
                <p className="text-xs font-semibold uppercase text-[var(--color-accent)]">
                  Body
                </p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--color-text-muted)]">
                  {result.original_script.body}
                </p>
              </div>

              {/* Payoff */}
              <div>
                <p className="text-xs font-semibold uppercase text-[var(--color-accent)]">
                  Payoff
                </p>
                <p className="mt-1 text-sm leading-relaxed">
                  {result.original_script.payoff}
                </p>
              </div>

              {/* Personalized version */}
              <div className="rounded-lg bg-[var(--color-bg)] p-3">
                <p className="text-xs font-semibold uppercase text-[var(--color-success)]">
                  Personalized Script
                </p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed text-[var(--color-text-muted)]">
                  {result.personalized_script}
                </p>
              </div>

              {/* Meta */}
              <div className="flex gap-4 text-xs text-[var(--color-text-muted)]">
                <span>
                  Duration: ~{result.original_script.estimated_duration.toFixed(0)}s
                </span>
                {result.original_script.structural_notes && (
                  <span>Notes: {result.original_script.structural_notes}</span>
                )}
              </div>

              {/* Video generation */}
              <VideoGenerator runId={runId} scriptId={result.script_id} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </Card>
  );
}

// ── Video Prompt List ─────────────────────────────────────

function VideoPromptList({ results }: { results: FinalResult[] }) {
  return (
    <div className="space-y-4">
      {results.map((result) => (
        <Card key={result.script_id}>
          <div className="flex items-start gap-3">
            <span
              className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold ${
                result.rank === 1
                  ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                  : "bg-[var(--color-border)] text-[var(--color-text-muted)]"
              }`}
            >
              {result.rank}
            </span>
            <div className="min-w-0 flex-1">
              <p className="whitespace-pre-wrap text-sm leading-relaxed text-[var(--color-text-muted)]">
                {result.video_prompt}
              </p>
              <p className="mt-2 font-mono text-xs text-[var(--color-text-muted)]">
                {result.script_id.slice(0, 12)} — {result.original_script.pattern_used}
              </p>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

// ── Video Generator ───────────────────────────────────────

function VideoGenerator({
  runId,
  scriptId,
}: {
  runId: string;
  scriptId: string;
}) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<VideoStatus | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clean up polling on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setError(null);

    try {
      const { job_id } = await generateVideo(runId, scriptId);
      setJobId(job_id);

      // Start polling
      pollRef.current = setInterval(async () => {
        try {
          const vs = await getVideoStatus(runId, job_id);
          setStatus(vs);

          if (vs.status === "complete" || vs.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setGenerating(false);

            if (vs.status === "failed") {
              setError(vs.error || "Video generation failed");
            }
          }
        } catch {
          // Keep polling on transient errors
        }
      }, 5000);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to start generation",
      );
      setGenerating(false);
    }
  }, [runId, scriptId]);

  return (
    <div className="border-t border-[var(--color-border)] pt-3">
      {!jobId && (
        <Button
          onClick={handleGenerate}
          loading={generating}
          size="sm"
          variant="secondary"
        >
          Generate Video
        </Button>
      )}

      {jobId && status?.status === "processing" && (
        <div className="flex items-center gap-2">
          <Spinner size="sm" />
          <span className="text-sm text-[var(--color-text-muted)]">
            Generating video...
          </span>
        </div>
      )}

      {status?.status === "complete" && status.video_url && (
        <VideoPlayer url={status.video_url} />
      )}

      {error && (
        <p className="mt-2 text-sm text-[var(--color-error)]">{error}</p>
      )}
    </div>
  );
}

// ── Video Player ──────────────────────────────────────────

function VideoPlayer({ url }: { url: string }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="overflow-hidden rounded-lg"
    >
      <video
        src={url}
        controls
        className="w-full rounded-lg"
        preload="metadata"
      >
        <track kind="captions" />
        Your browser does not support video playback.
      </video>
    </motion.div>
  );
}
