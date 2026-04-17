/**
 * Prompt Preview — live view of the actual LLM prompt, rendered with
 * the Creator Profile fields the user has typed so far.
 *
 * Reads the form via DOM events (the form lives in create.astro; we
 * avoid porting it to React just to share state). Fetches prompt
 * templates once from /api/prompts/preview.
 *
 * Four stages are visible via tabs:
 *   S1 Analyze  — no profile input (read-only info)
 *   S3 Generate — no profile input (read-only info)
 *   S4 Vote     — no profile input (read-only info)
 *   S6 Personalize — THE reason this panel exists; uses every profile field
 *
 * In S6, each profile field the user fills in highlights in-place in
 * the prompt so you can literally see where your words end up. Empty
 * fields render as muted `{placeholder}` tokens. Runtime-only fields
 * (the candidate script from S3) always render as muted placeholders
 * since the user can't control them.
 */

import { useEffect, useMemo, useState } from "react";
import { getPromptTemplates, type PromptTemplates } from "../lib/api-client";

// ── Field model ────────────────────────────────────────────

interface ProfileState {
  tone: string;
  vocabulary: string;
  catchphrases: string;
  topics_to_avoid: string;
  niche: string;
  audience_description: string;
  content_themes: string;
  example_hooks: string;
  recent_topics: string;
}

const EMPTY: ProfileState = {
  tone: "",
  vocabulary: "",
  catchphrases: "",
  topics_to_avoid: "",
  niche: "",
  audience_description: "",
  content_themes: "",
  example_hooks: "",
  recent_topics: "",
};

/** Form fields used by S6. Color keyed for the visual connection. */
const FIELD_COLOR: Record<keyof ProfileState, string> = {
  tone: "#7C3AED",
  vocabulary: "#2563EB",
  catchphrases: "#DB2777",
  topics_to_avoid: "#DC2626",
  niche: "#EA580C",
  audience_description: "#0891B2",
  content_themes: "#16A34A",
  example_hooks: "#CA8A04",
  recent_topics: "#6B7280",
};

// ── DOM observer ───────────────────────────────────────────

function readProfileFromDOM(): ProfileState {
  const getVal = (id: string): string =>
    (document.getElementById(id) as HTMLInputElement | HTMLTextAreaElement | null)?.value || "";
  return {
    tone: getVal("tone"),
    vocabulary: getVal("vocabulary"),
    catchphrases: getVal("catchphrases"),
    topics_to_avoid: getVal("topics_to_avoid"),
    niche: getVal("niche"),
    audience_description: getVal("audience_description"),
    content_themes: getVal("content_themes"),
    example_hooks: getVal("example_hooks"),
    recent_topics: getVal("recent_topics"),
  };
}

// ── S6 render ──────────────────────────────────────────────

type Segment =
  | { kind: "text"; text: string }
  | { kind: "field"; field: keyof ProfileState; value: string }
  | { kind: "placeholder"; label: string };

/** Build the S6 preview as a segmented sequence ready for React rendering. */
function buildS6Segments(template: string, profile: ProfileState): Segment[] {
  // The S6 template has two special tokens that are *computed* from profile
  // fields on the backend before the LLM sees the prompt:
  //   {creator_context} — a multi-line block from niche / audience /
  //     content_themes / example_hooks / recent_topics
  //   {niche_instruction} — a one-liner injected when niche is present
  // We expand both inline here so the user sees the FULL prompt.
  const ctxLines: string[] = [];
  if (profile.niche) ctxLines.push(`Niche: ${profile.niche}`);
  if (profile.audience_description)
    ctxLines.push(`Target audience: ${profile.audience_description}`);
  if (profile.content_themes)
    ctxLines.push(`Content themes: ${profile.content_themes}`);
  if (profile.example_hooks)
    ctxLines.push(`Hooks that worked before: ${profile.example_hooks}`);
  if (profile.recent_topics)
    ctxLines.push(`Recently covered (avoid repeating): ${profile.recent_topics}`);
  const contextInjected = ctxLines.length > 0;

  const nicheInstructionInjected = !!profile.niche;

  // Walk the template and emit segments. The template uses
  // str.format() semantics: {field} or {{literal braces}}.
  const segs: Segment[] = [];
  const len = template.length;
  let i = 0;
  let buf = "";
  const flushText = () => {
    if (buf) {
      segs.push({ kind: "text", text: buf });
      buf = "";
    }
  };

  while (i < len) {
    const ch = template[i];
    // Escaped braces: {{ or }}
    if ((ch === "{" || ch === "}") && template[i + 1] === ch) {
      buf += ch;
      i += 2;
      continue;
    }
    if (ch !== "{") {
      buf += ch;
      i++;
      continue;
    }
    // Found a placeholder {...}
    const end = template.indexOf("}", i + 1);
    if (end === -1) {
      buf += ch;
      i++;
      continue;
    }
    const key = template.slice(i + 1, end);
    flushText();

    // Case: runtime-only fields — always placeholders.
    const RUNTIME_PLACEHOLDERS: Record<string, string> = {
      hook: "hook from your winning script",
      body: "body from your winning script",
      payoff: "payoff from your winning script",
      pattern_used: "pattern used",
      estimated_duration: "25",
    };
    if (key in RUNTIME_PLACEHOLDERS) {
      segs.push({ kind: "placeholder", label: RUNTIME_PLACEHOLDERS[key] });
    }
    // Case: {creator_context} — expand inline.
    else if (key === "creator_context") {
      if (contextInjected) {
        segs.push({ kind: "text", text: "\n## Creator Context\n" });
        for (const [lineKey, rawLine] of extractContextLines(ctxLines)) {
          segs.push({ kind: "text", text: lineKey + ": " });
          segs.push({ kind: "field", field: rawLine.field, value: rawLine.value });
          segs.push({ kind: "text", text: "\n" });
        }
      }
    }
    // Case: {niche_instruction}
    else if (key === "niche_instruction") {
      if (nicheInstructionInjected) {
        segs.push({ kind: "text", text: " Ground the content in the creator's niche (" });
        segs.push({ kind: "field", field: "niche", value: profile.niche });
        segs.push({
          kind: "text",
          text: ") — use domain-specific references their audience expects.",
        });
      }
    }
    // Case: named field matches profile state key
    else if (key in EMPTY) {
      const fieldKey = key as keyof ProfileState;
      const value = profile[fieldKey];
      if (value) {
        segs.push({ kind: "field", field: fieldKey, value });
      } else {
        segs.push({ kind: "placeholder", label: fieldKey });
      }
    } else {
      // Unknown token — render as placeholder literally.
      segs.push({ kind: "placeholder", label: key });
    }
    i = end + 1;
  }
  flushText();
  return segs;
}

/** Map the pre-formatted context-line strings back onto their source fields
 * so we can colorize each one. Keeps buildS6Segments readable. */
function extractContextLines(
  lines: string[],
): Array<[string, { field: keyof ProfileState; value: string }]> {
  const out: Array<[string, { field: keyof ProfileState; value: string }]> = [];
  for (const line of lines) {
    const [label, ...rest] = line.split(": ");
    const value = rest.join(": ");
    const map: Record<string, keyof ProfileState> = {
      Niche: "niche",
      "Target audience": "audience_description",
      "Content themes": "content_themes",
      "Hooks that worked before": "example_hooks",
      "Recently covered (avoid repeating)": "recent_topics",
    };
    const field = map[label] as keyof ProfileState;
    if (field) out.push([label, { field, value }]);
  }
  return out;
}

// ── Segment renderer ───────────────────────────────────────

function RenderSegments({ segments }: { segments: Segment[] }) {
  return (
    <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-[var(--color-text)]">
      {segments.map((seg, i) => {
        if (seg.kind === "text") return <span key={i}>{seg.text}</span>;
        if (seg.kind === "placeholder") {
          return (
            <span
              key={i}
              className="rounded px-1 py-px text-[var(--color-text-light)] bg-[var(--color-border)]/30"
              style={{ fontStyle: "italic" }}
            >
              {"{" + seg.label + "}"}
            </span>
          );
        }
        // field
        const color = FIELD_COLOR[seg.field];
        return (
          <span
            key={i}
            data-field={seg.field}
            className="rounded px-1 py-px font-medium"
            style={{
              backgroundColor: `${color}20`,
              color,
              border: `1px solid ${color}60`,
            }}
            title={`from the "${seg.field}" field`}
          >
            {seg.value}
          </span>
        );
      })}
    </pre>
  );
}

// ── Non-S6 tabs: raw template with explainer ───────────────

function RawTemplate({ label, template }: { label: string; template: string }) {
  return (
    <div className="space-y-3">
      <div className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-[11px] leading-relaxed text-[var(--color-text-muted)]">
        {label}
      </div>
      <pre className="whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-[var(--color-text)]">
        {renderTemplateWithPlaceholders(template)}
      </pre>
    </div>
  );
}

function renderTemplateWithPlaceholders(template: string) {
  const segs: Array<{ kind: "text" | "ph"; v: string }> = [];
  const len = template.length;
  let i = 0;
  let buf = "";
  const flush = () => {
    if (buf) {
      segs.push({ kind: "text", v: buf });
      buf = "";
    }
  };
  while (i < len) {
    const ch = template[i];
    if ((ch === "{" || ch === "}") && template[i + 1] === ch) {
      buf += ch;
      i += 2;
      continue;
    }
    if (ch !== "{") {
      buf += ch;
      i++;
      continue;
    }
    const end = template.indexOf("}", i + 1);
    if (end === -1) {
      buf += ch;
      i++;
      continue;
    }
    flush();
    segs.push({ kind: "ph", v: template.slice(i + 1, end) });
    i = end + 1;
  }
  flush();
  return segs.map((s, idx) =>
    s.kind === "text" ? (
      <span key={idx}>{s.v}</span>
    ) : (
      <span
        key={idx}
        className="rounded px-1 py-px text-[var(--color-text-light)] bg-[var(--color-border)]/30"
        style={{ fontStyle: "italic" }}
      >
        {"{" + s.v + "}"}
      </span>
    ),
  );
}

// ── Main component ─────────────────────────────────────────

type Tab = "s6" | "s1" | "s3" | "s4";

export default function PromptPreview() {
  const [templates, setTemplates] = useState<PromptTemplates | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [profile, setProfile] = useState<ProfileState>(EMPTY);
  const [tab, setTab] = useState<Tab>("s6");

  useEffect(() => {
    let cancelled = false;
    getPromptTemplates()
      .then((t) => {
        if (!cancelled) setTemplates(t);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Observe the form via bubbling input events.
  useEffect(() => {
    const form = document.getElementById("create-form");
    if (!form) return;
    const update = () => setProfile(readProfileFromDOM());
    update();
    form.addEventListener("input", update);
    form.addEventListener("change", update);
    return () => {
      form.removeEventListener("input", update);
      form.removeEventListener("change", update);
    };
  }, []);

  const s6Segments = useMemo(() => {
    if (!templates) return [];
    return buildS6Segments(templates.s6, profile);
  }, [templates, profile]);

  if (error) {
    return (
      <div className="rounded-lg border border-[var(--color-error)]/30 bg-[var(--color-error)]/5 p-4 font-ui text-sm text-[var(--color-error)]">
        Failed to load prompt templates: {error}
      </div>
    );
  }

  if (!templates) {
    return (
      <div className="font-ui text-sm text-[var(--color-text-muted)]">
        Loading prompt preview…
      </div>
    );
  }

  return (
    <div className="space-y-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      {/* Header + tabs */}
      <div>
        <div className="flex items-baseline justify-between">
          <h3 className="font-display text-sm tracking-[0.12em]">Prompt Preview</h3>
          <span className="font-ui text-[10px] uppercase tracking-[0.12em] text-[var(--color-text-muted)]">
            What the LLM sees
          </span>
        </div>
        <div className="mt-3 flex gap-1 border-b border-[var(--color-border)]">
          {(
            [
              ["s6", "S6 Personalize"],
              ["s1", "S1 Analyze"],
              ["s3", "S3 Generate"],
              ["s4", "S4 Vote"],
            ] as Array<[Tab, string]>
          ).map(([id, label]) => {
            const active = tab === id;
            return (
              <button
                key={id}
                type="button"
                onClick={() => setTab(id)}
                className="relative -mb-px px-3 py-1.5 font-ui text-[11px] uppercase tracking-[0.08em] transition-colors"
                style={{
                  color: active ? "var(--color-ink)" : "var(--color-text-muted)",
                  borderBottom: active
                    ? "2px solid var(--stud-a)"
                    : "2px solid transparent",
                }}
              >
                {label}
                {id === "s6" && (
                  <span
                    className="ml-1 inline-block rounded-full px-1.5 py-px text-[8px]"
                    style={{ backgroundColor: "var(--stud-a)", color: "white" }}
                  >
                    you
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Body */}
      <div className="max-h-[70vh] overflow-y-auto">
        {tab === "s6" && (
          <div className="space-y-2">
            <p className="rounded-md border border-[var(--stud-a)]/30 bg-[var(--stud-d)]/30 p-2 font-ui text-[11px] text-[var(--stud-b)]">
              S6 is the only stage that reads your Creator Profile. Each
              colored span below is traceable back to a field in the form on
              the left.
            </p>
            <RenderSegments segments={s6Segments} />
          </div>
        )}
        {tab === "s1" && (
          <RawTemplate
            label="S1 analyzes each of the 100 videos in the dataset. It does not read your Creator Profile — the only inputs are the video's transcript, description, and engagement. Placeholders are filled from the dataset at runtime."
            template={templates.s1}
          />
        )}
        {tab === "s3" && (
          <RawTemplate
            label="S3 writes 20 candidate scripts from the pattern library produced by S2. It does not read your Creator Profile — by design, S3 produces universal viral patterns; your voice is layered on at S6."
            template={templates.s3}
          />
        )}
        {tab === "s4" && (
          <RawTemplate
            label="S4 has 42 simulated voter personas pick their top 5 scripts. It reads each voter's profile (from data/personas.json) but not yours. The scripts here come from S3."
            template={templates.s4}
          />
        )}
      </div>
    </div>
  );
}
