/**
 * A tool call's arguments and result, formatted (portalr ADR-0083): JSON laid out with its keys
 * and values told apart, and a string that holds lines, or code, as a block of its own, wrapped
 * to the box; or raw, as the run recorded them. Loaded as a call is first opened. Each part has
 * its own toggle; the latest choice is the default for the next, kept in this browser. Nothing
 * of a value is run or parsed as HTML: a string is shown as text, whatever it holds, with the
 * characters that would change the direction of what follows shown as their escapes. It
 * imports nothing the chat doesn't hold already, and takes the kit's parts it needs from its
 * caller, so the bundle shares no chunk between them.
 */

import { type ReactNode, useState } from "react";
import { Button } from "../button";
import { TYPE } from "../type";

/** The most characters formatted: past it, a value is shown raw, with a note. */
export const LONGEST = 200_000;

/** The deepest nesting, and the most values, laid out: past either, a value is shown raw. */
export const DEEPEST = 50;
export const MOST = 5000;

/** The most times a value cut short is cut back further to find what parses. */
const TRIES = 50;

/** How a text is parsed: as JSON, repaired where it was cut, or not at all, and why. */
export interface Parsed {
  readonly value: unknown;
  /** Whether it was cut short and closed, or cut back, to what parses. */
  readonly repaired: boolean;
}

/** Where `text`'s strings and nesting stand at its end, and where it could be cut back to. */
interface Scanned {
  readonly inString: boolean;
  readonly escaped: boolean;
  readonly stack: readonly string[];
  /** The last comma, and the last opening bracket, outside any string; -1 for none. */
  readonly comma: number;
  readonly open: number;
}

function scan(text: string): Scanned {
  const stack: string[] = [];
  let inString = false;
  let escaped = false;
  let comma = -1;
  let open = -1;
  for (let at = 0; at < text.length; at += 1) {
    const c = text[at];
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
      open = at;
    } else if (c === "}" || c === "]") {
      stack.pop();
    } else if (c === ",") {
      comma = at;
    }
  }
  return { inString, escaped, stack, comma, open };
}

/** What closes `text` where it stopped: its open string, then each open object and array. */
function closers(scanned: Scanned): string {
  const string = scanned.inString ? (scanned.escaped ? '\\"' : '"') : "";
  return string + [...scanned.stack].reverse().join("");
}

/** A number, `true`, `false` or `null` at the end of `text`, outside a string: cut, it is unknowable. */
const TOKEN_AT_END = /[-+.\deEa-z]+\s*$/i;

/**
 * The value `text` holds as JSON, or `undefined` where it holds none. A text cut short
 * (`cut`), mid-string or mid-object, is closed where it stopped and, failing that, cut back to
 * its last comma or opening bracket outside any string, and closed again, so what parses is
 * shown; a number or a word cut short at its end goes, as it can't be known. `repaired` says so.
 */
export function parseJson(text: string, cut = false): Parsed | undefined {
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
    let scanned = scan(rest);
    // Where the text itself stopped, a number or a word may be cut: later cuts end at a comma.
    if (tries === 0 && !scanned.inString && TOKEN_AT_END.test(rest)) {
      rest = rest.replace(TOKEN_AT_END, "");
      scanned = scan(rest);
    }
    try {
      return { value: JSON.parse(rest + closers(scanned)), repaired: true };
    } catch {
      const { comma, open } = scanned;
      if (comma < 0 && open < 0) {
        return undefined;
      }
      rest = comma > open ? rest.slice(0, comma) : rest.slice(0, open + 1);
    }
  }
  return undefined;
}

/** Whether `value` nests deeper, or holds more values, than is laid out: walked without recursion. */
export function tooHeavy(value: unknown): boolean {
  const stack: { value: unknown; depth: number }[] = [{ value, depth: 1 }];
  let count = 0;
  while (stack.length > 0) {
    const next = stack.pop() as { value: unknown; depth: number };
    count += 1;
    if (count > MOST || next.depth > DEEPEST) {
      return true;
    }
    if (next.value !== null && typeof next.value === "object") {
      for (const item of Object.values(next.value)) {
        stack.push({ value: item, depth: next.depth + 1 });
      }
    }
  }
  return false;
}

/** A number of sixteen digits or more, or in exponent form, which the browser may round. */
const LONG_NUMBER = /(?:^|[^\w."])-?\d{16,}|\d[eE][+-]?\d/;

/** The words a key is made of: `source_html` is `source` and `html`. */
const wordsOf = (key: string) => new Set(key.toLowerCase().split(/[^a-z0-9]+/));

/** The languages a key's words name, by the word. */
const NAMED: Readonly<Record<string, string>> = {
  html: "html",
  css: "css",
  style: "css",
  styles: "css",
  stylesheet: "css",
  js: "javascript",
  javascript: "javascript",
  ts: "typescript",
  typescript: "typescript",
  py: "python",
  python: "python",
  sql: "sql",
  md: "markdown",
  markdown: "markdown",
  code: "",
  source: "",
  src: "",
  script: "",
};

/**
 * The language a string value is written in: by its key's words first (`source_ts` names
 * TypeScript; `description` names nothing, as `script` is no word of it), then by its first
 * lines; "" for code of a language neither says, and null for prose.
 */
export function languageOf(key: string, value: string): string | null {
  // A language the key names wins; a word that says code alone, as `source`, comes after.
  const named = [...wordsOf(key)].map((word) => NAMED[word]).filter((it) => it !== undefined);
  const language = named.find((it) => it !== "") ?? named[0];
  if (language) {
    return language;
  }
  const head = value.trimStart().slice(0, 200);
  const lower = head.toLowerCase();
  if (lower.startsWith("<!doctype") || lower.startsWith("<html")) {
    return "html";
  }
  if (/^import .+ from ['"]|^(?:const|let|var|function) /m.test(head)) {
    return "javascript";
  }
  if (/^(?:def |class \w+[:(]|from \w+ import |import \w+\s*$)/m.test(head)) {
    return "python";
  }
  return language ?? (/^<[a-z!]/i.test(head) ? "" : null);
}

/** A string past which it is shown as a block of its own, wrapped, rather than in its line. */
const LONG = 80;

/**
 * `text` with each character that would change the direction, or the order, of what follows
 * shown as its escape, so a value reads as it is.
 */
const plain = (text: string) =>
  text.replace(/[‎‏‪-‮⁦-⁩]/g, (c) => `\\u${(c.codePointAt(0) ?? 0).toString(16).padStart(4, "0")}`);

/** What a part's caller gives it of the kit: the region a value scrolls in, and a Copy of it. */
export interface Shell {
  readonly region: (children: ReactNode) => ReactNode;
  readonly copy: (text: string, what?: string) => ReactNode;
}

/** A block of code, labelled by its language, wrapped to the box, with Copy; never highlighted. */
function Code({ code, language, copy }: { code: string; language: string; copy: Shell["copy"] }) {
  return (
    <div className="flex min-w-0 flex-col rounded-(--code-block-radius) border border-line bg-surface">
      <div className="flex items-center justify-between gap-2 border-line border-b py-1 pr-1 pl-3">
        <span className="font-mono text-muted text-xs">{language || "code"}</span>
        {copy(code, `this ${language || "code"} value`)}
      </div>
      <pre className="m-0 whitespace-pre-wrap break-words px-(--code-block-pad-x) py-(--code-block-pad-y) text-fg [font-variant-ligatures:none]">
        {plain(code)}
      </pre>
    </div>
  );
}

/** One of a JSON value's scalars, in its line. */
function Scalar({ value }: { value: unknown }) {
  return (
    <span className={typeof value === "string" ? "text-fg" : "text-accent"}>
      {plain(JSON.stringify(value))}
    </span>
  );
}

/**
 * A JSON value, laid out: an object's keys quiet before their values, each value on its line,
 * nested values indented, and a string that holds lines, code, or more than a line's worth as a
 * block of its own under its key, wrapped to the box. A string's content is shown as it is, its
 * escapes undone, never changed and never run.
 */
function Value({ value, name, copy }: { value: unknown; name: string; copy: Shell["copy"] }) {
  if (typeof value === "string" && (value.includes("\n") || value.length > LONG)) {
    const language = languageOf(name, value);
    return (
      <div className="mt-1 min-w-0">
        {language === null ? (
          <pre className="whitespace-pre-wrap break-words rounded-(--code-block-radius) border border-line bg-surface px-(--code-block-pad-x) py-(--code-block-pad-y)">
            {plain(value)}
          </pre>
        ) : (
          <Code code={value} language={language} copy={copy} />
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
            <Value value={item} name={name} copy={copy} />
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
            <span className="text-muted">{plain(JSON.stringify(key))}</span>
            <span className="text-muted">: </span>
            <Value value={item} name={key} copy={copy} />
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

/** Where the view chosen last is kept, as the default for the next part, in this browser. */
const KEY = "portalr:tool-call-view";

/** The view kept, or formatted; storage that can't be read is as nothing kept. */
function kept(): View {
  try {
    return localStorage.getItem(KEY) === "raw" ? "raw" : "formatted";
  } catch {
    return "formatted";
  }
}

/** Keep `view` as the default for the next part; storage that can't be written keeps nothing. */
function keep(view: View): void {
  try {
    view === "raw" ? localStorage.setItem(KEY, "raw") : localStorage.removeItem(KEY);
  } catch {
    // Without storage the choice lasts as long as this part.
  }
}

/** What a text is, once read: its value, laid out, or why it is shown as recorded. */
function read(text: string, cut: boolean): { parsed?: Parsed; note?: string } {
  const parsed = parseJson(text, cut);
  if (parsed === undefined) {
    return text.length > LONGEST ? { note: "Too long to format: shown as recorded." } : {};
  }
  if (tooHeavy(parsed.value)) {
    return { note: "Too much to format: shown as recorded." };
  }
  return { parsed };
}

/**
 * A part of a call, as the add-on draws it: its name, a Formatted and Raw toggle where the value
 * is an object or an array, Copy of what is shown, a note where the value was cut short or
 * holds numbers the browser may have rounded, and the value in its region. Formatted lays the
 * JSON out; Raw is the JSON indented, or the text as recorded.
 */
export function Formatted({
  name,
  what,
  text,
  shown,
  cut,
  shell,
}: {
  /** The part's name, such as "Arguments". */
  name: string;
  /** What it is, such as "the arguments of create_app", which names the toggle. */
  what: string;
  /** The value, as the run recorded it. */
  text: string;
  /** The raw view: the JSON indented, or the text as recorded. */
  shown: string;
  /** Whether the run cut it short. */
  cut: boolean;
  shell: Shell;
}) {
  const [view, setView] = useState(kept);
  // Read once the part is open, and again only when its text changes.
  const [was, setWas] = useState(() => ({ text, ...read(text, cut) }));
  if (was.text !== text) {
    setWas({ text, ...read(text, cut) });
  }
  const { parsed, note } = was;
  const toggles = parsed !== undefined && parsed.value !== null && typeof parsed.value === "object";
  const formatted = toggles && view === "formatted";
  const choose = (chosen: View) => {
    setView(chosen);
    keep(chosen);
  };
  return (
    <div className="flex flex-col gap-1">
      <div className="flex min-h-7 items-center justify-between gap-2">
        <span className={TYPE.note}>{name}</span>
        <span className="flex items-center gap-1">
          {toggles && (
            <fieldset aria-label={`View of ${what}`} className="m-0 flex gap-1 border-0 p-0">
              {(["formatted", "raw"] as const).map((choice) => (
                <Button
                  key={choice}
                  variant="ghost"
                  size="sm"
                  aria-pressed={view === choice}
                  onClick={() => choose(choice)}
                >
                  {choice === "raw" ? "Raw" : "Formatted"}
                </Button>
              ))}
            </fieldset>
          )}
          {/* Copy copies what is shown: the JSON laid out, as indented; Raw, as recorded. */}
          {shell.copy(toggles && view === "raw" ? text : shown)}
        </span>
      </div>
      {parsed?.repaired && (
        <p className={TYPE.note}>Cut short: values at the end may be incomplete.</p>
      )}
      {formatted && LONG_NUMBER.test(text) && (
        <p className={TYPE.note}>Long numbers may be rounded here: Raw has them as recorded.</p>
      )}
      {note && <p className={TYPE.note}>{note}</p>}
      {shell.region(
        formatted ? (
          <div className="min-w-0 break-words p-3 font-mono text-xs">
            <Value value={parsed.value} name="" copy={shell.copy} />
          </div>
        ) : (
          <pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs">{shown}</pre>
        ),
      )}
      {cut && <p className={TYPE.note}>Cut short: the run keeps the first part of each value.</p>}
    </div>
  );
}
