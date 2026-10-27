/**
 * The tools a run called, in its thread: each a summary that opens to what it was asked and what
 * it returned. Closed, it says the tool's name, how it is going, and a line of its arguments, or,
 * once it failed or was refused, of why. It follows the run as each call returns.
 */

import type { Artifactr } from "@portalr/client";
import type { ReactNode } from "react";
import { useState } from "react";
import { CopyButton } from "./copy-button";
import { Disclosure } from "./disclosure";
import { Icon } from "./icon";
import { glyphs } from "./icons";
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

/** One call: a summary line that opens to its arguments and what it returned; `open` to start so. */
export function ToolCall({
  tool,
  open = false,
  index,
}: {
  tool: Artifactr.Tool;
  open?: boolean;
  /** Its number in a run's ledger of steps (portalr ADR-0081): then a row of the ledger, unboxed. */
  index?: number;
}) {
  const [tone, word, returned] = STATUS[tool.status] ?? ["done", tool.status, "Result"];
  const failed = tool.status === "error" || tool.status === "retry";
  const line = failed ? tool.result : tool.args;
  const step = index !== undefined;
  return (
    <li>
      <Disclosure
        look="block"
        defaultOpen={open}
        className={
          step
            ? "text-sm"
            : "rounded-(--tool-call-radius) border border-line bg-surface text-sm data-open:border-edge"
        }
        triggerClassName="min-h-10 items-center rounded-(--tool-call-radius) px-(--tool-call-pad-x) py-(--tool-call-pad-y) hover:bg-transparent"
        panelClassName="data-open:pt-0"
        summary={
          <>
            {step ? (
              <span
                aria-hidden="true"
                className="w-4 shrink-0 text-end font-mono text-muted text-xs tabular-nums"
              >
                {index}
              </span>
            ) : (
              <Icon icon={glyphs.wrench} className="size-3.5 shrink-0 text-muted" />
            )}
            <code className="shrink-0 font-mono">{tool.name}</code>
            <span className="min-w-0 flex-1 truncate font-mono text-muted text-xs">{line}</span>
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

/** How a run's steps are going together: failed if any did, running while one is, else done. */
function stepsStatus(tools: readonly Artifactr.Tool[], running: boolean): readonly [Tone, string] {
  if (tools.some((tool) => tool.status === "error" || tool.status === "retry")) {
    return ["failed", "Failed"];
  }
  const called = tools.filter((tool) => tool.status === "called").length;
  if (running) {
    // Between one call's answer and the next, the run is still at work.
    const step =
      called > 0 ? `Running step ${tools.length - called + 1} of ${tools.length}` : "Working";
    return ["working", step];
  }
  return ["done", "Done"];
}

/**
 * A run's calls as one group (portalr ADR-0080): a summary that says how many steps and how
 * they are going, open while the run is, with the newest step open too, and folded once it is
 * done, so a run of eight calls is one line of the thread until it is wanted. One call is its
 * own row, as before.
 */
export function RunSteps({
  tools,
  running,
}: {
  tools: readonly (readonly [string, Artifactr.Tool])[];
  running: boolean;
}) {
  // Open while the run is, and folded as it ends; opened or closed by the reader meanwhile.
  const [open, setOpen] = useState(running);
  const [wasRunning, setWasRunning] = useState(running);
  if (wasRunning !== running) {
    setWasRunning(running);
    setOpen(running);
  }
  if (tools.length === 1) {
    return (
      <ToolCalls>
        <ToolCall tool={(tools[0] as [string, Artifactr.Tool])[1]} />
      </ToolCalls>
    );
  }
  const [tone, word] = stepsStatus(
    tools.map(([, tool]) => tool),
    running,
  );
  const latest = tools.at(-1)?.[1];
  return (
    <li>
      <Disclosure
        look="block"
        name={`${tools.length} steps`}
        open={open}
        onOpenChange={setOpen}
        className="rounded-(--tool-call-radius) border border-line bg-surface text-sm data-open:border-edge"
        triggerClassName="min-h-10 items-center rounded-(--tool-call-radius) px-(--tool-call-pad-x) py-(--tool-call-pad-y) hover:bg-transparent"
        panelClassName="data-open:pt-0"
        summary={
          <>
            <Icon icon={glyphs.terminal} className="size-3.5 shrink-0 text-muted" />
            <span className="shrink-0 font-semibold">{tools.length} steps</span>
            {latest && (
              <code className="min-w-0 flex-1 truncate font-mono text-muted text-xs">
                {latest.name}
              </code>
            )}
            <StatusBadge tone={tone} live={running} className="shrink-0">
              {word}
            </StatusBadge>
          </>
        }
      >
        <ol aria-label="Steps" className="flex flex-col border-line border-t py-1">
          {tools.map(([call, tool], at) => (
            <ToolCall
              key={call}
              tool={tool}
              index={at + 1}
              open={running && at === tools.length - 1}
            />
          ))}
        </ol>
      </Disclosure>
    </li>
  );
}
