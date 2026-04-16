/**
 * Results View — V2 campaign output display.
 *
 * V2 output is TEXT, not images: video scripts (hook/body/payoff),
 * personalized versions in the creator's voice, and video prompts
 * for AI video generation models.
 *
 * Design: V1 aesthetic (Bebas Neue + Cormorant Garamond + DM Sans)
 * adapted for text-first output.
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
        if (!cancelled) { setResults(data); setLoading(false); }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load results");
          setLoading(false);
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, [runId]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-4">
        <Spinner size="lg" />
        <p className="font-body text-lg text-[var(--color-text-muted)]">
          Loading your campaign...
        </p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-[10px] border border-[var(--eval-c)] bg-[var(--eval-d)]/30 p-8 text-center">
        <p className="font-display text-xl tracking-[0.08em] text-[var(--eval-b)]">
          Failed to Load
        </p>
        <p className="mt-2 font-body text-base text-[var(--color-text-muted)]">{error}</p>
        <a
          href={`/pipeline/?id=${runId}`}
          className="mt-4 inline-block font-ui text-[11px] uppercase tracking-[0.1em] text-[var(--stud-b)] hover:underline"
        >
          Check pipeline status
        </a>
      </div>
    );
  }

  if (!results || results.results.length === 0) {
    return (
      <div className="py-20 text-center">
        <p className="font-body text-lg text-[var(--color-text-muted)]">
          No results found for this run.
        </p>
      </div>
    );
  }

  // Winner script for the hero section
  const winner = results.results[0];

  return (
    <div className="space-y-8">
      {/* Hero — winning script */}
      <div className="text-center">
        <p className="font-ui text-[10px] uppercase tracking-[0.18em] text-[var(--color-text-light)]">
          Top ranked by {results.results.length > 1 ? "audience vote" : "evaluation"}
        </p>
        <h2 className="font-display text-[clamp(28px,5vw,48px)] tracking-[0.06em] mt-2">
          Campaign Results
        </h2>
        {winner && (
          <p className="font-body mx-auto mt-3 max-w-lg text-lg text-[var(--color-text-muted)]">
            &ldquo;{winner.original_script.hook}&rdquo;
          </p>
        )}
      </div>

      {/* Tabs */}
      <Tabs
        tabs={[
          {
            id: "scripts",
            label: `Scripts (${results.results.length})`,
            content: <ScriptList results={results.results} runId={runId} />,
          },
          {
            id: "prompts",
            label: "Video Prompts",
            content: <VideoPromptList results={results.results} />,
          },
        ]}
      />
    </div>
  );
}

// ── Script List ───────────────────────────────────────────

function ScriptList({ results, runId }: { results: FinalResult[]; runId: string }) {
  return (
    <div className="space-y-5">
      {results.map((result) => (
        <ScriptCard key={result.script_id} result={result} runId={runId} />
      ))}
    </div>
  );
}

// ── Script Card ───────────────────────────────────────────

function ScriptCard({ result, runId }: { result: FinalResult; runId: string }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <Card padding="lg">
      <div className="space-y-4">
        {/* Rank header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <span
              className="flex h-10 w-10 items-center justify-center rounded-full font-display text-lg"
              style={{
                backgroundColor: result.rank === 1 ? "var(--eval-d)" : "rgba(14,12,20,0.04)",
                color: result.rank === 1 ? "var(--eval-b)" : "var(--color-text-muted)",
              }}
            >
              {result.rank}
            </span>
            <div>
              <span className="font-ui text-[10px] uppercase tracking-[0.1em] text-[var(--color-text-light)]">
                {result.original_script.pattern_used}
              </span>
              <div className="flex items-center gap-3 mt-0.5">
                <span className="font-ui text-[10px] text-[var(--eval-a)]">
                  {result.vote_score.toFixed(1)} votes
                </span>
                <span className="font-ui text-[10px] text-[var(--color-text-light)]">
                  ~{result.original_script.estimated_duration.toFixed(0)}s
                </span>
              </div>
            </div>
          </div>
          <button
            onClick={() => setExpanded((s) => !s)}
            className="font-ui text-[10px] uppercase tracking-[0.1em] text-[var(--color-text-muted)] hover:text-[var(--color-ink)] transition-colors"
          >
            {expanded ? "Collapse" : "Expand"}
          </button>
        </div>

        {/* Hook — always visible, hero treatment */}
        <div>
          <p className="font-ui text-[9px] uppercase tracking-[0.14em] text-[var(--disc-b)]">
            Hook
          </p>
          <p className="font-body mt-1 text-xl leading-relaxed">
            {result.original_script.hook}
          </p>
        </div>

        {/* Expanded: Body + Payoff + Personalized + Video Prompt */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: "auto" }}
              exit={{ opacity: 0, height: 0 }}
              className="space-y-5 overflow-hidden"
            >
              {/* Body */}
              <div>
                <p className="font-ui text-[9px] uppercase tracking-[0.14em] text-[var(--stud-b)]">
                  Body
                </p>
                <p className="font-body mt-1 text-base leading-relaxed text-[var(--color-text-muted)]">
                  {result.original_script.body}
                </p>
              </div>

              {/* Payoff */}
              <div>
                <p className="font-ui text-[9px] uppercase tracking-[0.14em] text-[var(--stud-b)]">
                  Payoff
                </p>
                <p className="font-body mt-1 text-base leading-relaxed">
                  {result.original_script.payoff}
                </p>
              </div>

              {/* Personalized Script — the creator's voice version */}
              <div className="rounded-[10px] bg-[var(--pers-d)]/30 border border-[var(--pers-c)]/40 p-5">
                <p className="font-ui text-[9px] uppercase tracking-[0.14em] text-[var(--pers-b)]">
                  In Your Voice
                </p>
                <p className="font-body mt-2 whitespace-pre-wrap text-base leading-relaxed text-[var(--color-text-muted)]">
                  {result.personalized_script}
                </p>
              </div>

              {/* Structural notes */}
              {result.original_script.structural_notes && (
                <p className="font-ui text-[10px] text-[var(--color-text-light)]">
                  {result.original_script.structural_notes}
                </p>
              )}

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
    <div className="space-y-5">
      {results.map((result) => (
        <Card key={result.script_id} padding="lg">
          <div className="flex items-start gap-4">
            <span
              className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full font-display text-sm"
              style={{
                backgroundColor: result.rank === 1 ? "var(--pers-d)" : "rgba(14,12,20,0.04)",
                color: result.rank === 1 ? "var(--pers-b)" : "var(--color-text-muted)",
              }}
            >
              {result.rank}
            </span>
            <div className="min-w-0 flex-1">
              <p className="font-ui text-[9px] uppercase tracking-[0.14em] text-[var(--pers-b)] mb-2">
                Video Production Prompt
              </p>
              <p className="font-body whitespace-pre-wrap text-base leading-relaxed text-[var(--color-text-muted)]">
                {result.video_prompt}
              </p>
              <div className="mt-3 flex items-center gap-3">
                <span className="font-ui text-[10px] uppercase tracking-[0.08em] text-[var(--color-text-light)]">
                  {result.original_script.pattern_used}
                </span>
                <span className="font-ui text-[10px] text-[var(--color-text-light)]">
                  ~{result.original_script.estimated_duration.toFixed(0)}s
                </span>
              </div>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

// ── Video Generator ───────────────────────────────────────

function VideoGenerator({ runId, scriptId }: { runId: string; scriptId: string }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [status, setStatus] = useState<VideoStatus | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const handleGenerate = useCallback(async () => {
    setGenerating(true);
    setError(null);
    try {
      const { job_id } = await generateVideo(runId, scriptId);
      setJobId(job_id);
      pollRef.current = setInterval(async () => {
        try {
          const vs = await getVideoStatus(runId, job_id);
          setStatus(vs);
          if (vs.status === "complete" || vs.status === "failed") {
            if (pollRef.current) clearInterval(pollRef.current);
            pollRef.current = null;
            setGenerating(false);
            if (vs.status === "failed") setError(vs.error || "Video generation failed");
          }
        } catch { /* keep polling */ }
      }, 5000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start generation");
      setGenerating(false);
    }
  }, [runId, scriptId]);

  return (
    <div className="border-t border-[var(--color-border)] pt-4">
      {!jobId && (
        <Button onClick={handleGenerate} loading={generating} size="sm" variant="secondary">
          Generate Video
        </Button>
      )}
      {jobId && status?.status === "processing" && (
        <div className="flex items-center gap-3">
          <Spinner size="sm" />
          <span className="font-body text-sm text-[var(--color-text-muted)]">
            Generating video...
          </span>
        </div>
      )}
      {status?.status === "complete" && status.video_url && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="overflow-hidden rounded-[10px]">
          <video src={status.video_url} controls className="w-full rounded-[10px]" preload="metadata">
            <track kind="captions" />
          </video>
        </motion.div>
      )}
      {error && <p className="mt-2 font-ui text-[11px] text-[var(--eval-a)]">{error}</p>}
    </div>
  );
}
