/**
 * A tool call's arguments and result, formatted (portalr ADR-0083): JSON laid out with its keys
 * and values told apart, and a string that holds lines, or code, as a block of its own, wrapped
 * to the box; or raw, as the run recorded them. Loaded as a call is first opened. The choice is
 * one for every call, kept in this browser. Nothing of a value is run or parsed as HTML: a
 * string is shown as text, whatever it holds.
 */

import { type ReactNode, useEffect, useState } from "react";
import { Button } from "../button";
import { cn } from "../cn";
import { CodeBlock } from "../code-block";

/** The most characters formatted: past it, a value is shown raw, with a note. */
export const LONGEST = 200_000;

/** The most times a value cut short is cut back further to find what parses. */
const TRIES = 50;

/**
 * The value `text` holds as JSON, or `undefined` where it holds none. A text cut short
 * (`cut`), mid-string or mid-object, is closed where it stopped and, failing that, cut back to
 * its last boundary and closed again, so what parses is shown; `repaired` says so.
 */
export function parseJson(
  text: string,
  cut = false,
): { readonly value: unknown; readonly repaired: boolean } | undefined {
  if (text.length > LONGEST || text.trim() === "") {
    return undefined;
  }
  try {
    return { value: JSON.parse(text), repaired: false };
  } catch {
    if (!cut) {
      return undefined;
    }
  }
  let rest = text;
  for (let tries = 0; tries < TRIES; tries += 1) {
    try {
      return { value: JSON.parse(rest + closers(rest)), repaired: true };
    } catch {
      const comma = rest.lastIndexOf(",");
      const open = Math.max(rest.lastIndexOf("{"), rest.lastIndexOf("["));
      if (Math.max(comma, open) <= 0) {
        return undefined;
      }
      rest = comma > open ? rest.slice(0, comma) : rest.slice(0, open + 1);
    }
  }
  return undefined;
}

/** What closes `text` where it stopped: its open string, then each open object and array. */
function closers(text: string): string {
  const stack: string[] = [];
  let inString = false;
  let escaped = false;
  for (const c of text) {
    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (c === "\\") {
        escaped = true;
      } else if (c === '"') {
        inString = false;
      }
    } else if (c === '"') {
      inString = true;
    } else if (c === "{" || c === "[") {
      stack.push(c === "{" ? "}" : "]");
    } else if (c === "}" || c === "]") {
      stack.pop();
    }
  }
  return (inString ? (escaped ? '\\"' : '"') : "") + stack.reverse().join("");
}

/** The language a string value is written in, by its key's name and its first characters. */
export function languageOf(key: string, value: string): string | null {
  const name = key.toLowerCase();
  const head = value.trimStart().slice(0, 64).toLowerCase();
  if (/html/.test(name) || head.startsWith("<!doctype") || head.startsWith("<html")) {
    return "html";
  }
  if (/css|style/.test(name)) {
    return "css";
  }
  if (/\b(js|javascript|script)\b|_js$/.test(name)) {
    return "javascript";
  }
  if (/\b(ts|typescript)\b|_ts$/.test(name)) {
    return "typescript";
  }
  if (/\b(py|python)\b/.test(name) || head.startsWith("def ") || head.startsWith("import ")) {
    return "python";
  }
  if (/sql/.test(name)) {
    return "sql";
  }
  if (/markdown|\bmd\b/.test(name)) {
    return "markdown";
  }
  if (/code|source|src|script/.test(name) || head.startsWith("<")) {
    return "";
  }
  return null;
}

/** A string past which it is shown as a block of its own, wrapped, rather than in its line. */
const LONG = 80;

/** One of a JSON value's scalars, in its line. */
function Scalar({ value }: { value: unknown }) {
  return (
    <span className={typeof value === "string" ? "text-fg" : "text-accent"}>
      {JSON.stringify(value)}
    </span>
  );
}

/**
 * A JSON value, laid out: an object's keys quiet before their values, each value on its line,
 * nested values indented, and a string that holds lines, code, or more than a line's worth as a
 * block of its own under its key, wrapped to the box. A string's content is shown as it is, its
 * escapes undone, never changed and never run.
 */
function Value({ value, name }: { value: unknown; name: string }): ReactNode {
  if (typeof value === "string" && (value.includes("\n") || value.length > LONG)) {
    const language = languageOf(name, value);
    return (
      <div className="my-1 min-w-0">
        {language === null ? (
          <pre className="whitespace-pre-wrap break-words rounded-(--code-block-radius) border border-line bg-surface px-(--code-block-pad-x) py-(--code-block-pad-y)">
            {value}
          </pre>
        ) : (
          <CodeBlock code={value} language={language} />
        )}
      </div>
    );
  }
  if (Array.isArray(value)) {
    return value.length === 0 ? (
      <Scalar value={[]} />
    ) : (
      <Nested open="[" close="]">
        {value.map((item, at) => (
          // Items have no key of their own: their place is their identity.
          <Entry key={at} last={at === value.length - 1}>
            <Value value={item} name={name} />
          </Entry>
        ))}
      </Nested>
    );
  }
  if (value !== null && typeof value === "object") {
    const entries = Object.entries(value);
    return entries.length === 0 ? (
      <Scalar value={{}} />
    ) : (
      <Nested open="{" close="}">
        {entries.map(([key, item], at) => (
          <Entry key={key} last={at === entries.length - 1}>
            <span className="text-muted">{JSON.stringify(key)}</span>
            <span className="text-muted">: </span>
            <Value value={item} name={key} />
          </Entry>
        ))}
      </Nested>
    );
  }
  return <Scalar value={value} />;
}

/** An object's or an array's entries, indented between its brackets. */
function Nested({ open, close, children }: { open: string; close: string; children: ReactNode }) {
  return (
    <>
      <span className="text-muted">{open}</span>
      <div className="min-w-0 ps-4">{children}</div>
      <span className="text-muted">{close}</span>
    </>
  );
}

/** One entry, on its line, with its comma unless it is the last. */
function Entry({ last, children }: { last: boolean; children: ReactNode }) {
  return (
    <div className="min-w-0">
      {children}
      {!last && <span className="text-muted">,</span>}
    </div>
  );
}

export type View = "formatted" | "raw";

/** Where the view chosen is kept, for every call, in this browser. */
const KEY = "portalr:tool-call-view";

/** The view kept, or formatted; storage that can't be read is as nothing kept. */
function kept(): View {
  try {
    return localStorage.getItem(KEY) === "raw" ? "raw" : "formatted";
  } catch {
    return "formatted";
  }
}

/** The open calls of this tab, told when the view changes in any of them. */
const followers = new Set<(view: View) => void>();

/**
 * The view, shared by every open call of this tab, and kept for the browser: as
 * `stored-setting` keeps a choice, but without its chunk, which the budget hasn't room for.
 * Storage that can't be written keeps the choice as long as the page.
 */
function useView(): readonly [View, (view: View) => void] {
  const [view, setView] = useState(kept);
  useEffect(() => {
    followers.add(setView);
    return () => {
      followers.delete(setView);
    };
  }, []);
  return [
    view,
    (chosen) => {
      try {
        chosen === "raw" ? localStorage.setItem(KEY, "raw") : localStorage.removeItem(KEY);
      } catch {
        // Without storage the choice lasts as long as the page.
      }
      for (const follow of followers) {
        follow(chosen);
      }
    },
  ];
}

/** What a part of a call shows: its text, formatted, or the raw view its caller draws. */
export function Formatted({
  text,
  cut,
  what,
  raw,
}: {
  /** The value, as the run recorded it. */
  text: string;
  /** Whether the run cut it short. */
  cut: boolean;
  /** What it is, such as "the arguments of create_app", which names the toggle. */
  what: string;
  /** The raw view, as its caller draws it. */
  raw: ReactNode;
}) {
  const [view, setView] = useView();
  // Parsed once the part is open, and again only when its text changes.
  const [parsed, setParsed] = useState(() => ({ text, found: parseJson(text, cut) }));
  if (parsed.text !== text) {
    setParsed({ text, found: parseJson(text, cut) });
  }
  const { found } = parsed;
  return (
    <>
      {found !== undefined && (
        <fieldset aria-label={`View of ${what}`} className="m-0 flex gap-1 border-0 p-0">
          {(["formatted", "raw"] as const).map((choice) => (
            <Button
              key={choice}
              variant="ghost"
              size="sm"
              aria-pressed={view === choice}
              onClick={() => setView(choice)}
            >
              {choice === "raw" ? "Raw" : "Formatted"}
            </Button>
          ))}
        </fieldset>
      )}
      {found !== undefined && view === "formatted" ? (
        <div className={cn("min-w-0 break-words p-3 font-mono text-xs", found.repaired && "")}>
          <Value value={found.value} name="" />
        </div>
      ) : (
        raw
      )}
      {found?.repaired && (
        <p className="px-3 pb-2 text-muted text-xs">Formatted from what parses of it.</p>
      )}
      {found === undefined && text.length > LONGEST && (
        <p className="px-3 pb-2 text-muted text-xs">Too long to format: shown as recorded.</p>
      )}
    </>
  );
}
