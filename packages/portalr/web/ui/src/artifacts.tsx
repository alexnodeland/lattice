/**
 * Artifacts, by kind: a registry of renderers an application extends with its own kinds, and
 * formatted JSON for any kind without one, so a new kind is never invisible (lattice RFC-0002).
 * Text renders through `Markdown`, never as HTML. A kind's renderer also says what of its data
 * a revision's changes are read from, and how finely (portalr ADR-0017).
 */

import type { Change, Granularity } from "@portalr/client";
import type { ReactNode } from "react";
import { cn } from "./cn";
import { Markdown } from "./markdown";

/** An artifact's data, as artifactr holds it. */
export type Data = Readonly<Record<string, unknown>>;

export interface Renderer {
  /** The artifact's data, shown. */
  render(data: Data): ReactNode;
  /** The text a revision's changes are read from. */
  text(data: Data): string;
  /**
   * A short title for the artifact, as plain text, or null if its data hold none: pure, cheap,
   * at most `LONGEST_TITLE` characters, and never throws on data of any shape.
   */
  title(data: Data): string | null;
  /** How finely those changes are cut. */
  readonly diff: Granularity;
}

/** The application's renderers, by artifact kind. */
export type Renderers = ReadonlyMap<string, Renderer>;

/** The longest a title is, in characters: a longer one is cut, with an ellipsis. */
export const LONGEST_TITLE = 80;

/**
 * Text as a one-line title: the first line with words in it, without Markdown's marks (a
 * heading's `#`, a list's or a quote's marker, emphasis, code, a link's address), white space
 * collapsed, cut to `LONGEST_TITLE`. Null where nothing is left.
 */
export function plainTitle(text: string): string | null {
  const line = text.split(/\r?\n/).find((each) => /[\p{L}\p{N}]/u.test(each)) ?? "";
  const plain = line
    .replace(/^\s*(?:#{1,6}\s+|>+\s*|[-*+]\s+|\d+[.)]\s+)/, "")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[`*_~]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!/[\p{L}\p{N}]/u.test(plain)) {
    return null;
  }
  const chars = [...plain];
  return chars.length > LONGEST_TITLE ? `${chars.slice(0, LONGEST_TITLE - 1).join("")}…` : plain;
}

/** Any kind without a renderer: its data as JSON, changed line by line; titled by its `title`. */
export const json: Renderer = {
  render: (data) => (
    <pre className="overflow-x-auto rounded-md bg-paper p-3 font-mono text-fg text-xs">
      {JSON.stringify(data, null, 2)}
    </pre>
  ),
  text: (data) => JSON.stringify(data, null, 2),
  title: (data) => (typeof data.title === "string" ? plainTitle(data.title) : null),
  diff: "lines",
};

/** A kind whose data holds Markdown in one field, `text` unless named: changed word by word. */
export function markdown(field = "text"): Renderer {
  const text = (data: Data) => {
    const value = data[field];
    return typeof value === "string" ? value : "";
  };
  return {
    render: (data) => <Markdown>{text(data)}</Markdown>,
    text,
    title: (data) => plainTitle(text(data)),
    diff: "words",
  };
}

/** The renderer for a kind: the application's, or JSON. */
export function rendererFor(kind: string, renderers: Renderers): Renderer {
  return renderers.get(kind) ?? json;
}

/** An artifact's content, through its kind's renderer. */
export function ArtifactContent({
  kind,
  data,
  renderers,
}: {
  kind: string;
  data: Data;
  renderers: Renderers;
}) {
  return <>{rendererFor(kind, renderers).render(data)}</>;
}

/**
 * What changed between two versions: what was added, and what was removed, marked as such; or,
 * when `client` found them too large to compare, that.
 */
export function Diff({
  changes,
  className,
}: {
  changes: readonly Change[] | null;
  className?: string;
}) {
  if (changes === null) {
    return <p className={cn("text-muted text-sm italic", className)}>Too large to compare.</p>;
  }
  return (
    <p className={cn("whitespace-pre-wrap text-fg text-sm", className)}>
      {changes.map((change, index) => {
        const key = `${index}:${change.kind}`;
        switch (change.kind) {
          case "added":
            return (
              <ins
                key={key}
                className="rounded-sm bg-wash px-0.5 text-fg underline decoration-2 decoration-accent underline-offset-3"
              >
                <span className="sr-only">added: </span>
                {change.text}
              </ins>
            );
          case "removed":
            return (
              <del key={key} className="mr-1 text-muted line-through">
                <span className="sr-only">removed: </span>
                {change.text}
              </del>
            );
          default:
            return <span key={key}>{change.text}</span>;
        }
      })}
    </p>
  );
}
