/**
 * SSE client — React hook for pipeline event streaming.
 *
 * Opens an EventSource to /api/pipeline/status/{runId}.
 * Reconnects automatically using Last-Event-ID.
 * Multi-tab safe (backend uses Redis Streams, not BLPOP).
 *
 * Contract: https://github.com/yangyang-how/flair2/issues/71 Section 2.
 */

import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = import.meta.env.PUBLIC_API_URL || "http://localhost:8000";

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

// ── Hook ───────────────────────────────────────────────────

export function useSSE(runId: string | null): SSEState {
  const [state, setState] = useState<SSEState>({
    event: null,
    events: [],
    connected: false,
    error: null,
  });

  const eventSourceRef = useRef<EventSource | null>(null);
  const lastEventIdRef = useRef<string | null>(null);

  const connect = useCallback(() => {
    if (!runId) return;

    const url = `${API_BASE}/api/pipeline/status/${runId}`;
    const es = new EventSource(url);
    eventSourceRef.current = es;

    es.onopen = () => {
      setState((prev) => ({ ...prev, connected: true, error: null }));
    };

    es.onmessage = (msg) => {
      // Default "message" event type — shouldn't happen with our backend
      // but handle gracefully
      try {
        const data = JSON.parse(msg.data);
        const sseEvent: SSEEvent = {
          id: msg.lastEventId || "",
          event: "message",
          data,
          timestamp: data.timestamp || new Date().toISOString(),
        };
        lastEventIdRef.current = msg.lastEventId;
        setState((prev) => ({
          ...prev,
          event: sseEvent,
          events: [...prev.events, sseEvent],
        }));
      } catch {
        // Malformed event — skip
      }
    };

    es.onerror = () => {
      es.close();
      setState((prev) => ({
        ...prev,
        connected: false,
        error: "Connection lost. Reconnecting...",
      }));

      // Reconnect after 2s. Browser EventSource auto-reconnects,
      // but we close explicitly on terminal events, so manual reconnect
      // is only for error cases.
      setTimeout(() => connect(), 2000);
    };

    // Listen for all named event types from the contract
    const eventTypes = [
      "pipeline_started",
      "stage_started",
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

          lastEventIdRef.current = msg.lastEventId;

          setState((prev) => ({
            ...prev,
            event: sseEvent,
            events: [...prev.events, sseEvent],
            // Clear error on successful event
            error: TERMINAL_EVENTS.has(type)
              ? type === "pipeline_error"
                ? (data.data?.error ?? "Pipeline failed")
                : null
              : null,
          }));

          // Close connection on terminal events
          if (TERMINAL_EVENTS.has(type)) {
            es.close();
            setState((prev) => ({ ...prev, connected: false }));
          }
        } catch {
          // Malformed event — skip
        }
      });
    }
  }, [runId]);

  useEffect(() => {
    connect();

    return () => {
      eventSourceRef.current?.close();
      eventSourceRef.current = null;
    };
  }, [connect]);

  return state;
}
