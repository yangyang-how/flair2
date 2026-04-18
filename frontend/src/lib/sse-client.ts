/**
 * SSE client — React hook for pipeline event streaming.
 *
 * Opens an EventSource to /api/pipeline/status/{runId}.
 *
 * Resume semantics:
 *   - Native EventSource auto-reconnects on transient network errors
 *     and re-sends its own Last-Event-ID header. No extra work needed
 *     for that path.
 *   - For COMPONENT REMOUNT (SPA navigation back to the same runId,
 *     or deliberate tab refocus on an in-flight run), the browser
 *     drops its internal Last-Event-ID. We persist the last-seen ID
 *     per-runId in a module-level Map and pass it as `?cursor=<id>`
 *     on fresh EventSource connections. Backend prefers this over the
 *     header.
 *
 * Multi-tab safe (backend uses Redis Streams, not BLPOP).
 *
 * Contract: https://github.com/yangyang-how/flair2/issues/71 Section 2.
 */

import { useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.PUBLIC_API_URL || "";

// Cross-mount memory of last-seen event IDs. Lives for the lifetime of
// the module (≈ the tab's JS runtime), which is the right scope for
// "user navigated away and came back".
const lastSeenByRunId: Map<string, string> = new Map();

// ── Types ──────────────────────────────────────────────────

export interface SSEEvent {
  id: string;
  event: string;
  data: Record<string, unknown>;
  timestamp: string;
}

interface SSEState {
  event: SSEEvent | null;
  events: SSEEvent[];
  connected: boolean;
  error: string | null;
}

// Terminal events — close connection after receiving these
const TERMINAL_EVENTS = new Set(["pipeline_complete", "pipeline_error"]);

// Cap event history to prevent unbounded memory growth
const MAX_EVENT_HISTORY = 500;

// ── Hook ───────────────────────────────────────────────────

export function useSSE(runId: string | null): SSEState {
  const [state, setState] = useState<SSEState>({
    event: null,
    events: [],
    connected: false,
    error: null,
  });

  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    if (!runId) return;

    // If we've seen events for this runId in this session already,
    // resume from the last one we got instead of replaying from "0-0".
    const cursor = lastSeenByRunId.get(runId);
    const url = cursor
      ? `${API_BASE}/api/pipeline/status/${runId}?cursor=${encodeURIComponent(cursor)}`
      : `${API_BASE}/api/pipeline/status/${runId}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    const recordId = (id: string) => {
      if (id) lastSeenByRunId.set(runId, id);
    };

    const pushEvent = (sseEvent: SSEEvent) => {
      recordId(sseEvent.id);
      setState((prev) => ({
        ...prev,
        event: sseEvent,
        events:
          prev.events.length >= MAX_EVENT_HISTORY
            ? [...prev.events.slice(-MAX_EVENT_HISTORY + 1), sseEvent]
            : [...prev.events, sseEvent],
        error: null,
      }));
    };

    es.onopen = () => {
      setState((prev) => ({ ...prev, connected: true, error: null }));
    };

    es.onerror = () => {
      // Don't close — let native EventSource retry handle reconnection.
      // It preserves Last-Event-ID automatically across retries.
      setState((prev) => ({
        ...prev,
        connected: false,
        error: "Connection lost. Reconnecting...",
      }));
    };

    es.onmessage = (msg) => {
      // Default "message" event type — shouldn't happen with our backend
      try {
        const data = JSON.parse(msg.data);
        pushEvent({
          id: msg.lastEventId || "",
          event: "message",
          data,
          timestamp: data.timestamp || new Date().toISOString(),
        });
      } catch {
        // Malformed — skip
      }
    };

    // Listen for all named event types from the contract
    const eventTypes = [
      "pipeline_started",
      "stage_started",
      "s1_task_started",
      "s1_progress",
      "s2_complete",
      "s3_progress",
      "s3_complete",
      "vote_cast",
      "s5_complete",
      "s6_progress",
      "pipeline_complete",
      "pipeline_error",
    ];

    for (const type of eventTypes) {
      es.addEventListener(type, (msg: MessageEvent) => {
        try {
          const data = JSON.parse(msg.data);
          const sseEvent: SSEEvent = {
            id: msg.lastEventId || "",
            event: type,
            data: typeof data.data === "object" ? data.data : data,
            timestamp: data.timestamp || new Date().toISOString(),
          };

          if (TERMINAL_EVENTS.has(type)) {
            // Terminal event — update state and close
            setState((prev) => ({
              ...prev,
              event: sseEvent,
              events:
                prev.events.length >= MAX_EVENT_HISTORY
                  ? [...prev.events.slice(-MAX_EVENT_HISTORY + 1), sseEvent]
                  : [...prev.events, sseEvent],
              connected: false,
              error:
                type === "pipeline_error"
                  ? (data.data?.error ?? "Pipeline failed")
                  : null,
            }));
            es.close();
          } else {
            pushEvent(sseEvent);
          }
        } catch {
          // Malformed — skip
        }
      });
    }

    return () => {
      es.close();
      eventSourceRef.current = null;
    };
  }, [runId]);

  return state;
}
