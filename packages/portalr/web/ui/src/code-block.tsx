import { type ReactNode, useState } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { CopyButton } from "./copy-button";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { ScrollRegion } from "./scroll-region";

type Props = {
  /** The code, as written: what is shown, and what Copy copies. */
  code: string;
  /** The fence's language, if it named one. */
  language: string;
  /** One quiet line under the code, such as why an add-on's block shows as its source. */
  note?: ReactNode;
  /** The code as drawn, highlighted; by default, the code as it is. */
  children?: ReactNode;
};

/**
 * A fenced block of code: its language, a toggle that wraps its long lines, and Copy, over the code
 * in a region that scrolls sideways and takes the focus, so a keyboard can scroll it too
 * (portalr ADR-0043).
 */
export function CodeBlock({ code, language, note, children }: Props) {
  const [wrapped, setWrapped] = useState(false);
  const named = language ? `${language} code` : "Code";
  const what = language ? `the ${language} code` : "the code";
  return (
    <div className="flex min-w-0 flex-col rounded-(--code-block-radius) border border-line bg-paper">
      <div className="flex items-center justify-between gap-2 border-line border-b py-1 pr-1 pl-3">
        <span className="font-mono text-muted text-xs">{language || "Code"}</span>
        <span className="flex gap-1">
          <Button
            variant="ghost"
            size="sm"
            aria-label={`Wrap ${what}`}
            aria-pressed={wrapped}
            onClick={() => setWrapped(!wrapped)}
          >
            <Icon icon={glyphs.wrapText} className="size-3.5" />
            Wrap
          </Button>
          <CopyButton text={code} what={what} />
        </span>
      </div>
      <ScrollRegion aria-label={named} className="-outline-offset-(--focus-offset)">
        <pre
          className={cn(
            "m-0 px-(--code-block-pad-x) py-(--code-block-pad-y) font-mono text-fg text-sm [font-variant-ligatures:none]",
            wrapped ? "whitespace-pre-wrap break-words" : "whitespace-pre",
          )}
        >
          <code>{children ?? code}</code>
        </pre>
      </ScrollRegion>
      {note && <p className="border-line border-t px-3 py-1.5 text-muted text-xs">{note}</p>}
    </div>
  );
}
