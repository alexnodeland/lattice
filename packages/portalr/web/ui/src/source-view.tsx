import { WrapText } from "lucide-react";
import { useId, useMemo, useState } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { CopyButton } from "./copy-button";
import { Token, useHighlightedLines } from "./highlighting";
import { Icon } from "./icon";
import { ScrollRegion } from "./scroll-region";

/** The most lines shown before the rest are asked for. */
export const FOLDED_LINES = 40;

/**
 * A whole source, such as a mini app's HTML, to read: its lines numbered, highlighted where `ui`
 * highlights its language, with a toggle that wraps its long lines and Copy, and beyond
 * `FOLDED_LINES` lines folded until the reader asks for the rest (portalr ADR-0054). Each line is
 * a row of its own, so a wrapped line keeps its number beside its start. The numbers are drawn,
 * not read: a screen reader reads the code alone, as Copy copies it.
 */
export function SourceView({
  code,
  language,
  name,
}: {
  /** The source, as written. */
  code: string;
  /** Its language, as a fence names one; `ui` highlights the ones it knows. */
  language: string;
  /** What it is, for its region and its controls: "HTML" names "HTML source", "Copy the HTML". */
  name: string;
}) {
  const what = `the ${name}`;
  const [wrapped, setWrapped] = useState(false);
  const [unfolded, setUnfolded] = useState(false);
  const highlighted = useHighlightedLines(code, language);
  const region = useId();
  // Each line with its number, which is its identity: a source's lines are only read whole. A
  // newline that ends the source ends its last line, and starts no other.
  const plain = useMemo(
    () =>
      (code.endsWith("\n") ? code.slice(0, -1) : code)
        .split(/\r?\n/)
        .map((text, number) => ({ text, number })),
    [code],
  );
  const count = plain.length;
  const folded = !unfolded && count > FOLDED_LINES;
  const shown = folded ? FOLDED_LINES : count;
  const digits = String(count).length;
  return (
    <div className="flex min-w-0 flex-col rounded-md border border-line bg-paper">
      <div className="flex flex-wrap items-center justify-between gap-2 border-line border-b py-1 ps-3 pe-1">
        <span className="text-xs">
          <span className="inline-block font-semibold text-fg first-letter:uppercase">{name}</span>
          <span className="text-muted">
            {" "}
            · {language} · {code === "" ? "empty" : count === 1 ? "1 line" : `${count} lines`}
          </span>
        </span>
        <span className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Wrap ${what}`}
            aria-pressed={wrapped}
            onClick={() => setWrapped(!wrapped)}
          >
            <Icon icon={WrapText} className="size-3.5" />
            Wrap
          </Button>
          <CopyButton text={code} what={what} />
        </span>
      </div>
      <ScrollRegion aria-label={`${name} source`} className="outline-offset-[-2px]">
        <pre
          id={region}
          // Left to right whatever the page's direction: code reads that way.
          dir="ltr"
          className={cn(
            "m-0 grid py-2 font-mono text-fg text-sm [font-variant-ligatures:none]",
            wrapped ? "grid-cols-[auto_minmax(0,1fr)]" : "w-max min-w-full grid-cols-[auto_1fr]",
          )}
        >
          {plain.slice(0, shown).map(({ text, number: at }) => (
            <span key={at} className="contents">
              <span
                aria-hidden="true"
                className="select-none ps-3 pe-3 text-end text-muted"
                style={{ minWidth: `${digits + 2}ch` }}
              >
                {at + 1}
              </span>
              <code
                className={cn(
                  "pe-3",
                  wrapped ? "whitespace-pre-wrap break-words" : "whitespace-pre",
                )}
              >
                {highlighted?.[at]
                  ? highlighted[at].map((token) => <Token key={token.offset} token={token} />)
                  : text}
                {at < shown - 1 && "\n"}
              </code>
            </span>
          ))}
        </pre>
      </ScrollRegion>
      {count > FOLDED_LINES && (
        <div className="border-line border-t px-1 py-1">
          <Button
            variant="ghost"
            size="sm"
            aria-controls={region}
            aria-expanded={!folded}
            onClick={() => setUnfolded(!unfolded)}
          >
            {folded ? `Show all ${count} lines` : `Show the first ${FOLDED_LINES} lines`}
          </Button>
        </div>
      )}
    </div>
  );
}
