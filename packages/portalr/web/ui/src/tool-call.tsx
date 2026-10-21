/**
 * The tools a run called, in its thread: each a summary that opens to what it was asked and what
 * it returned. Closed, it says the tool's name, how it is going, and a line of its arguments, or,
 * once it failed or was refused, of why. It follows the run as each call returns.
 */

import type { Artifactr } from "@portalr/client";
import { Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { CopyButton } from "./copy-button";
import { Disclosure } from "./disclosure";
import { Icon } from "./icon";
import { ScrollRegion } from "./scroll-region";
import { StatusBadge, type Tone } from "./status-badge";
import { TYPE } from "./type";

/** How a call is going, as a shape and a word, by the status its run recorded. */
const STATUS: Record<string, readonly [Tone, string, string]> = {
  // tone, the badge's word, and what the second part holds
  called: ["working", "Running", "Result"],
  ok: ["done", "Done", "Result"],
  error: ["failed", "Failed", "Error"],
  retry: ["retrying", "Refused", "Why it was refused"],
};

/** A value as it reads best: JSON indented, anything else as it was recorded. */
function pretty(text: string): string {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    return text;
  }
}

/**
 * A part of a call: its name, a way to copy it, and its value, scrolled where it is long, which
 * the keyboard reaches and scrolls too. A value the run cut short, at its limit, says so.
 */
function Part({
  name,
  tool,
  text,
  cut,
}: {
  name: string;
  tool: string;
  text: string;
  cut: boolean;
}) {
  const what = `the ${name.toLowerCase()} of ${tool}`;
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <span className={TYPE.note}>{name}</span>
        <CopyButton text={text} what={what} />
      </div>
      <ScrollRegion
        aria-label={what.charAt(0).toUpperCase() + what.slice(1)}
        className="max-h-64 overflow-y-auto rounded-(--tool-call-result-radius) border border-line bg-paper"
      >
        <pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs">{text}</pre>
      </ScrollRegion>
      {cut && <p className={TYPE.note}>Cut short: the run keeps the first part of each value.</p>}
    </div>
  );
}

/** One call: a summary line that opens to its arguments and what it returned. */
export function ToolCall({ tool }: { tool: Artifactr.Tool }) {
  const [tone, word, returned] = STATUS[tool.status] ?? ["done", tool.status, "Result"];
  const failed = tool.status === "error" || tool.status === "retry";
  const line = failed ? tool.result : tool.args;
  return (
    <li>
      <Disclosure
        look="block"
        className="rounded-(--tool-call-radius) border border-line bg-surface text-sm data-open:border-edge"
        triggerClassName="min-h-10 items-center rounded-(--tool-call-radius) px-(--tool-call-pad-x) py-(--tool-call-pad-y) hover:bg-transparent"
        panelClassName="data-open:pt-0"
        summary={
          <>
            <Icon icon={Wrench} className="size-3.5 shrink-0 text-muted" />
            <code className="shrink-0 font-mono">{tool.name}</code>
            <span className="min-w-0 flex-1 truncate text-muted text-xs">{line}</span>
            <StatusBadge tone={tone} className="shrink-0">
              {word}
            </StatusBadge>
          </>
        }
      >
        <div className="flex flex-col gap-3 border-line border-t p-3">
          <Part
            name="Arguments"
            tool={tool.name}
            text={pretty(tool.args) || "{}"}
            cut={tool.argsCut}
          />
          {tool.status !== "called" && (
            <Part
              name={returned}
              tool={tool.name}
              text={pretty(tool.result)}
              cut={tool.resultCut}
            />
          )}
        </div>
      </Disclosure>
    </li>
  );
}

/** A run's calls, as one list in its thread. */
export function ToolCalls({ children }: { children: ReactNode }) {
  return (
    <li>
      <ul aria-label="Tools" className="flex flex-col gap-1">
        {children}
      </ul>
    </li>
  );
}
