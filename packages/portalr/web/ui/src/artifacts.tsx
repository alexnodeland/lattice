/**
 * Artifacts, by kind: a registry of renderers an application extends with its own kinds, and
 * formatted JSON for any kind without one, so a new kind is never invisible (lattice RFC-0002).
 * Text renders through `Markdown`, never as HTML. A kind's renderer also says what of its data
 * a revision's changes are read from, and how finely (portalr ADR-0017), and, part by part, what
 * a revision shows as its source and its changes (portalr ADR-0054).
 */

import type { Change, Granularity } from "@portalr/client/diff";
import { createContext, type ReactNode } from "react";
import { cn } from "./cn";
import { JsonView } from "./json-view";
import { Markdown } from "./markdown";

/** An artifact's data, as artifactr holds it. */
export type Data = Readonly<Record<string, unknown>>;

/**
 * A part of a kind's data, as its revisions are read and compared: a title, a summary, a page's
 * HTML. One with a language is a source, which a revision shows, numbered and highlighted.
 */
export interface RevisionPart {
  /** What it is, in a sentence's words: "title", "HTML". */
  readonly name: string;
  readonly text: string;
  /** How finely its changes are cut. */
  readonly diff: Granularity;
  /** Its language, as a fence names one, where it is a source to read. */
  readonly language?: string;
}

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
  /**
   * Whether the thread it was made in shows it, inline, where it was made: once, at its latest
   * version. Every kind the kit draws is; one shown as JSON is reached from its own page alone,
   * and an application's own kind is shown inline by setting it (portalr ADR-0055).
   */
  readonly inline?: boolean;
  /** Its data in parts, as a revision reads and compares them; by default, its `text`, whole. */
  parts?(data: Data): readonly RevisionPart[];
  /** What a revision's preview shows of it; by default, what `render` does. */
  preview?(data: Data): ReactNode;
  /** A line about it, beside its title in a revision, such as an app's summary; or null. */
  about?(data: Data): string | null;
  /**
   * Whether showing it runs what it holds, as an app does: a list of its revisions runs one at a
   * time, when asked, and only where it may run.
   */
  readonly runs?: boolean;
}

/** The application's renderers, by artifact kind. */
export type Renderers = ReadonlyMap<string, Renderer>;

/** The longest a title is, in characters: a longer one is cut, with an ellipsis. */
export const LONGEST_TITLE = 80;

/** The most of a line a title is read from: its regular expressions run on no more than this. */
const READ = 400;

const HAS_WORDS = /[\p{L}\p{N}]/u;

/** Emphasis in underscores, which, as in CommonMark, never starts or ends inside a word. */
const UNDERSCORED = /(?<![\p{L}\p{N}_])(?:__|_)([^\n_]{1,200}?)(?:__|_)(?![\p{L}\p{N}_])/gu;

/** White space collapsed, and the text cut to `LONGEST_TITLE` code points, ellipsis included. */
export function capped(text: string): string | null {
  const plain = text.replace(/\s+/g, " ").trim();
  if (!HAS_WORDS.test(plain)) {
    return null;
  }
  const chars = [...plain];
  return chars.length > LONGEST_TITLE ? `${chars.slice(0, LONGEST_TITLE - 1).join("")}…` : plain;
}

/**
 * Markdown as a one-line title: the first line with words in it, without Markdown's marks (a
 * heading's `#`, a list's or a quote's marker, paired emphasis and code, a link's address), cut to
 * `LONGEST_TITLE`. Null where nothing is left. Only paired marks go, so `my_file_name` and `2*3`
 * stay as written; every pattern is bounded, and none reads more than `READ` characters of a line.
 */
export function plainTitle(text: string): string | null {
  const line = (text.split(/\r?\n/).find((each) => HAS_WORDS.test(each)) ?? "").slice(0, READ);
  return capped(
    line
      .replace(/^\s{0,3}(?:#{1,6}\s+|>+\s*|[-*+]\s+|\d{1,9}[.)]\s+)/, "")
      // A link's text, and its address up to 200 characters: a longer one is left as it is.
      .replace(/!?\[([^\]]{0,200})\]\([^)]{0,200}\)/g, "$1")
      // Paired marks that flank text: the opener before a non-space and not inside a word, the
      // closer after a non-space and not inside one, so "2*3 + 4*5" and "a * b * c" keep their
      // stars. Code is paired backticks, wherever they are.
      .replace(
        /(?<![\p{L}\p{N}*~])(\*\*|~~|\*)(?=\S)(.{1,200}?)(?<=\S)\1(?![\p{L}\p{N}*~])/gu,
        "$2",
      )
      .replace(/`([^`]{1,200})`/g, "$1")
      .replace(UNDERSCORED, "$1"),
  );
}

const pretty = (data: Data) => JSON.stringify(data, null, 2);

/**
 * Any kind without a renderer: its data as JSON, read as a tree, its strings unescaped; changed
 * line by line; titled by its `title`.
 */
export const json: Renderer = {
  render: (data) => <JsonView data={data} />,
  text: pretty,
  parts: (data) => [{ name: "JSON", text: pretty(data), diff: "lines", language: "json" }],
  // A JSON title is plain text, as written: only its white space and its length are ours.
  title: (data) => (typeof data.title === "string" ? capped(data.title.slice(0, READ)) : null),
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
    parts: (data) => [{ name: "Markdown", text: text(data), diff: "words", language: "markdown" }],
    title: (data) => plainTitle(text(data)),
    diff: "words",
    inline: true,
  };
}

/** A kind's data in parts, as its revisions are read and compared. */
export const partsOf = (renderer: Renderer, data: Data): readonly RevisionPart[] =>
  renderer.parts?.(data) ?? [{ name: "content", text: renderer.text(data), diff: renderer.diff }];

/** The renderer for a kind: the application's, or JSON. */
export function rendererFor(kind: string, renderers: Renderers): Renderer {
  return renderers.get(kind) ?? json;
}

/** An artifact, the version of it shown, and whether it is archived. */
export interface Shown {
  readonly id: string;
  readonly version: number;
  /** Whether it is archived, which switches an app off; a page that doesn't know says nothing. */
  readonly archived?: boolean;
}

/** The artifact being shown, and its version: what a renderer that acts on it, such as a form's, acts on. */
export const ShownContext = createContext<Shown | null>(null);

/**
 * An artifact's content, through its kind's renderer. Given which artifact it is, and at which
 * version (`shown`), a renderer that acts on the artifact, such as a form's, knows which and when.
 */
export function ArtifactContent({
  kind,
  data,
  renderers,
  shown,
}: {
  kind: string;
  data: Data;
  renderers: Renderers;
  shown?: Shown;
}) {
  const content = rendererFor(kind, renderers).render(data);
  return shown === undefined ? content : <ShownContext value={shown}>{content}</ShownContext>;
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
