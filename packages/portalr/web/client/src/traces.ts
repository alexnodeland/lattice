/**
 * A trace as a tree of spans a screen can draw: portalr's flat spans, ordered, with each one's
 * place in the trace, what it is, and what of it a person reads: tokens, a model, a tool, an
 * error, and what was said in it, if it was asked for (portalr ADR-0030).
 *
 * Spans are read by the OpenTelemetry GenAI conventions our libraries and pydantic-ai write,
 * `gen_ai.operation.name` and its siblings, not by AgentPrism's adapter, which takes OTLP whole.
 */

import type { components } from "./generated/portalr.openapi";

export type Trace = components["schemas"]["Trace"];
type Span = Trace["spans"][number];

/** What a span is, for the mark it takes and the word that names it. */
export type Kind = "workflow" | "agent" | "llm" | "tool" | "http" | "database" | "other";

/** What a `gen_ai.operation.name` says a span is. */
const OPERATIONS: Readonly<Record<string, Kind>> = {
  invoke_workflow: "workflow",
  invoke_agent: "agent",
  create_agent: "agent",
  chat: "llm",
  text_completion: "llm",
  generate_content: "llm",
  embeddings: "llm",
  execute_tool: "tool",
};

/** A span's kind: by its operation, else by what else it carries. */
export function kindOf(attributes: Span["attributes"]): Kind {
  const operation = attributes["gen_ai.operation.name"];
  if (typeof operation === "string" && Object.hasOwn(OPERATIONS, operation)) {
    return OPERATIONS[operation] ?? "other";
  }
  if ("http.request.method" in attributes || "http.method" in attributes) {
    return "http";
  }
  return "db.system" in attributes ? "database" : "other";
}

/** One span, placed in its trace. */
export interface Row {
  readonly id: string;
  readonly name: string;
  readonly kind: Kind;
  /** How deep it is: 0 for a root. */
  readonly depth: number;
  /** Whether any span is its child. */
  readonly parent: boolean;
  /** Its parent's id, or null for a root. */
  readonly parentId: string | null;
  /** Milliseconds after the trace began. */
  readonly offset: number;
  /** Milliseconds it took. */
  readonly duration: number;
  readonly error: boolean;
  readonly model: string | null;
  readonly tool: string | null;
  readonly tokens: { readonly input: number | null; readonly output: number | null } | null;
  readonly attributes: Span["attributes"];
  /** The names of the attributes it has that this read left out, as they aren't known to be safe. */
  readonly withheld: readonly string[];
}

/** One of a span's attributes that was withheld, read when its span was asked for. */
export interface Said {
  readonly label: string;
  readonly text: string;
}

/** A trace laid out: every span in order, its parents before its children, and how long it ran. */
export interface Outline {
  readonly rows: readonly Row[];
  /** False where the trace has more spans than portalr gives: these are its first. */
  readonly complete: boolean;
  /** Milliseconds from its first span's start to its last span's end. */
  readonly duration: number;
}

const NS_PER_MS = 1_000_000;

const number = (value: unknown): number | null => (typeof value === "number" ? value : null);
const text = (value: unknown): string | null => (typeof value === "string" ? value : null);

/**
 * A trace's spans in tree order: roots by start, each followed by its children by start. A span
 * whose parent isn't in the trace is a root. A span that is its own ancestor, or a cycle, is shown
 * as a root rather than lost, so a trace that is wrong is still read.
 */
export function outline(trace: Trace): Outline {
  const spans = trace.spans;
  const ids = new Set(spans.map((span) => span.span_id));
  const children = new Map<string | null, Span[]>();
  let start = Number.POSITIVE_INFINITY;
  let end = Number.NEGATIVE_INFINITY;
  for (const span of spans) {
    const parent = span.parent_id !== null && ids.has(span.parent_id) ? span.parent_id : null;
    const siblings = children.get(parent);
    if (siblings) {
      siblings.push(span);
    } else {
      children.set(parent, [span]);
    }
    start = Math.min(start, span.start_ns);
    end = Math.max(end, span.end_ns);
  }
  const rows: Row[] = [];
  const placed = new Set<string>();
  const place = (span: Span, depth: number) => {
    if (placed.has(span.span_id)) {
      return;
    }
    placed.add(span.span_id);
    const below = children.get(span.span_id) ?? [];
    // A span in a cycle may have a child already placed above it: that isn't one to open.
    const opens = below.some((child) => !placed.has(child.span_id));
    const { attributes } = span;
    const input = number(attributes["gen_ai.usage.input_tokens"]);
    const output = number(attributes["gen_ai.usage.output_tokens"]);
    rows.push({
      id: span.span_id,
      name: span.name,
      kind: kindOf(attributes),
      depth,
      parent: opens,
      parentId: span.parent_id,
      offset: (span.start_ns - start) / NS_PER_MS,
      duration: Math.max(0, span.end_ns - span.start_ns) / NS_PER_MS,
      error: span.error,
      model: text(attributes["gen_ai.request.model"]) ?? text(attributes["gen_ai.response.model"]),
      tool: text(attributes["gen_ai.tool.name"]),
      tokens: input === null && output === null ? null : { input, output },
      attributes,
      withheld: span.withheld ?? [],
    });
    for (const child of [...below].sort((a, b) => a.start_ns - b.start_ns)) {
      place(child, depth + 1);
    }
  };
  for (const root of [...(children.get(null) ?? [])].sort((a, b) => a.start_ns - b.start_ns)) {
    place(root, 0);
  }
  // What a cycle hid from every root: shown as roots.
  for (const span of spans) {
    place(span, 0);
  }
  return {
    rows,
    complete: trace.complete ?? true,
    duration: spans.length === 0 ? 0 : (end - start) / NS_PER_MS,
  };
}

/** What people call the attributes that most often hold what was said. */
const LABELS: Readonly<Record<string, string>> = {
  "gen_ai.system_instructions": "Instructions",
  "gen_ai.input.messages": "Prompt",
  "gen_ai.output.messages": "Completion",
  "gen_ai.tool.call.arguments": "Tool arguments",
  "gen_ai.tool.call.result": "Tool result",
};

/**
 * A span's attributes as a person reads them once they are asked for: each labelled, a name people
 * know by it, else by its own, its JSON, if it is JSON, indented; the labelled first.
 */
export function said(attributes: Span["attributes"], names: readonly string[]): Said[] {
  const labelled = (name: string) => Object.hasOwn(LABELS, name);
  return [...names]
    .filter((name) => Object.hasOwn(attributes, name))
    .sort((a, b) => Number(!labelled(a)) - Number(!labelled(b)) || a.localeCompare(b))
    .map((name) => {
      const value = String(attributes[name]);
      const label = LABELS[name] ?? name;
      try {
        return { label, text: JSON.stringify(JSON.parse(value), null, 2) };
      } catch {
        return { label, text: value };
      }
    });
}

/** A trace's id as portalr and Tempo write it: 32 lowercase hex digits where it is hex. */
export function wholeTrace(id: string): string {
  return /^[0-9a-f]{1,31}$/i.test(id) ? id.toLowerCase().padStart(32, "0") : id;
}
