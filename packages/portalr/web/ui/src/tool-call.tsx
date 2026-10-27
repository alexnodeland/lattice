/**
 * The tools a run called, in its thread: each a summary that opens to what it was asked and what
 * it returned. Closed, it says the tool's name, how it is going, and a line of its arguments, or,
 * once it failed or was refused, of why. It follows the run as each call returns.
 */

import type { Artifactr } from "@portalr/client";
import type { ReactNode } from "react";
import { useState } from "react";
import { Button } from "./button";
import { CopyButton } from "./copy-button";
import { Disclosure } from "./disclosure";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { useRetrying } from "./on-demand";
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

/** The formatted view of a call's parts (portalr ADR-0083), loaded as a call is first opened. */
const loadJsonView = () => import("./on-demand/json-view");

type JsonView = Awaited<ReturnType<typeof loadJsonView>>;

/**
 * A part of a call: its name, a way to copy what is shown, and its value, scrolled where it is
 * long, which the keyboard reaches and scrolls too: JSON indented, or, once `view` has loaded,
 * formatted, with a toggle to the raw view. A value the run cut short, at its limit, says so.
 */
function Part({
  name,
  tool,
  text,
  cut,
  view,
}: {
  name: string;
  tool: string;
  /** The value, as the run recorded it. */
  text: string;
  cut: boolean;
  view: JsonView | null;
}) {
  const what = `the ${name.toLowerCase()} of ${tool}`;
  // As recorded until the formatted view loads, which indents it; no arguments are `{}`.
  const shown = text || (name === "Arguments" ? "{}" : "");
  const region = (children: ReactNode) => (
    <ScrollRegion
      aria-label={what.charAt(0).toUpperCase() + what.slice(1)}
      className="max-h-64 overflow-y-auto rounded-(--tool-call-result-radius) border border-line bg-paper"
    >
      {children}
    </ScrollRegion>
  );
  if (view) {
    const copy = (copied: string, of = what) => <CopyButton text={copied} what={of} />;
    const choice = (label: string, pressed: boolean, onClick: () => void) => (
      <Button variant="ghost" size="sm" aria-pressed={pressed} onClick={onClick}>
        {label}
      </Button>
    );
    return (
      <view.Formatted
        name={name}
        what={what}
        text={shown}
        cut={cut}
        shell={{ region, copy, choice }}
      />
    );
  }
  return (
    <div className="flex flex-col gap-1">
      <div className="flex min-h-7 items-center justify-between gap-2">
        <span className={TYPE.note}>{name}</span>
        <CopyButton text={shown} what={what} />
      </div>
      {/* As recorded, unescaped: the add-on's escapes would cost the first load bytes it hasn't. */}
      {region(<pre className="whitespace-pre-wrap break-words p-3 font-mono text-xs">{shown}</pre>)}
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
  // The formatted view loads once the call is opened, by the reader or by a find in the page; one
  // that failed to load, as offline, is tried again as the call is opened again.
  const [opened, setOpened] = useState(open);
  const view = useRetrying(loadJsonView, opened, opened);
  return (
    <li>
      <Disclosure
        look="block"
        open={opened}
        onOpenChange={setOpened}
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
            <bdi className="min-w-0 flex-1 truncate font-mono text-muted text-xs">{line}</bdi>
            <StatusBadge tone={tone} className="shrink-0">
              {word}
            </StatusBadge>
          </>
        }
      >
        <div className="flex flex-col gap-3 border-line border-t p-3">
          <Part name="Arguments" tool={tool.name} text={tool.args} cut={tool.argsCut} view={view} />
          {tool.status !== "called" && (
            <Part
              name={returned}
              tool={tool.name}
              text={tool.result}
              cut={tool.resultCut}
              view={view}
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
