/**
 * API client — single module for all backend calls.
 *
 * Types mirror backend Pydantic models (app/models/).
 * All fetch() calls go through here — no raw fetch in components.
 *
 * Contract: https://github.com/yangyang-how/flair2/issues/78
 */

const API_BASE = import.meta.env.PUBLIC_API_URL || "http://localhost:8000";

// ── Types: Pipeline ────────────────────────────────────────

export interface CreatorProfile {
  tone: string;
  vocabulary: string[];
  catchphrases: string[];
  topics_to_avoid: string[];
  // Expanded fields — optional for backward compat (#70)
  niche?: string | null;
  audience_description?: string | null;
  content_themes?: string[];
  example_hooks?: string[];
  recent_topics?: string[];
}

export interface StartPipelineRequest {
  creator_profile: CreatorProfile;
  reasoning_model: string;
  video_model?: string | null;
  num_videos?: number;
  num_scripts?: number;
  num_personas?: number;
  top_n?: number;
}

export interface StartPipelineResponse {
  run_id: string;
}

export interface RunStatus {
  run_id: string;
  status: "pending" | "running" | "completed" | "failed";
  current_stage: string | null;
  stages: Record<string, string>;
}

export interface RunListResponse {
  runs: RunStatus[];
}

export interface CandidateScript {
  script_id: string;
  pattern_used: string;
  hook: string;
  body: string;
  payoff: string;
  estimated_duration: number;
  structural_notes: string;
}

export interface FinalResult {
  script_id: string;
  original_script: CandidateScript;
  personalized_script: string;
  video_prompt: string;
  rank: number;
  vote_score: number;
}

export interface PipelineResults {
  run_id: string;
  results: FinalResult[];
  creator_profile: CreatorProfile;
  completed_at: string;
}

// ── Types: Video ───────────────────────────────────────────

export interface VideoStatus {
  job_id: string;
  status: "processing" | "complete" | "failed";
  video_url?: string | null;
  error?: string | null;
}

// ── Types: Performance ─────────────────────────────────────

export interface SubmitPerformanceRequest {
  run_id: string;
  script_id: string;
  platform: string;
  post_url: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  watch_time_avg?: number | null;
  completion_rate?: number | null;
}

export interface PerformanceEntry {
  run_id: string;
  script_id: string;
  platform: string;
  post_url: string;
  posted_at: string;
  views: number;
  likes: number;
  comments: number;
  shares: number;
  watch_time_avg?: number | null;
  completion_rate?: number | null;
}

// ── Types: Providers ───────────────────────────────────────

export interface Providers {
  reasoning: string[];
  video: string[];
}

// ── Types: Insights ────────────────────────────────────────

export interface Insights {
  top_patterns: unknown[];
  prediction_accuracy: number | null;
  total_videos_tracked: number;
}

// ── API Error ──────────────────────────────────────────────

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public detail?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── Session ID ─────────────────────────────────────────────

const SESSION_KEY = "flair2_session_id";

/**
 * Get or create a persistent session ID.
 * Stored in localStorage so it survives page reloads but not
 * cross-browser/incognito. Good enough for a prototype.
 */
export function getSessionId(): string {
  if (typeof window === "undefined") return "ssr";
  let id = localStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

// ── Helpers ────────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(
      `${res.status} ${res.statusText}`,
      res.status,
      body.detail,
    );
  }

  return res.json();
}

// ── Pipeline ───────────────────────────────────────────────

export function startPipeline(
  req: StartPipelineRequest,
): Promise<StartPipelineResponse> {
  const sid = getSessionId();
  return request(`/api/pipeline/start?session_id=${sid}`, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function getPipelineResults(
  runId: string,
): Promise<PipelineResults> {
  return request(`/api/pipeline/results/${runId}`);
}

export function listRuns(): Promise<RunListResponse> {
  const sid = getSessionId();
  return request(`/api/runs?session_id=${sid}`);
}

// ── Providers ──────────────────────────────────────────────

export function getProviders(): Promise<Providers> {
  return request("/api/providers");
}

// ── Video ──────────────────────────────────────────────────

export function generateVideo(
  runId: string,
  scriptId: string,
): Promise<{ job_id: string }> {
  return request("/api/video/generate", {
    method: "POST",
    body: JSON.stringify({ run_id: runId, script_id: scriptId }),
  });
}

export function getVideoStatus(
  runId: string,
  jobId: string,
): Promise<VideoStatus> {
  return request(`/api/video/status/${runId}/${jobId}`);
}

// ── Performance ────────────────────────────────────────────

export function submitPerformance(
  req: SubmitPerformanceRequest,
): Promise<{ status: string }> {
  return request("/api/performance", {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function getPerformance(
  runId: string,
): Promise<{ run_id: string; performances: PerformanceEntry[] }> {
  return request(`/api/performance/${runId}`);
}

// ── Insights ───────────────────────────────────────────────

export function getInsights(): Promise<Insights> {
  return request("/api/insights");
}
