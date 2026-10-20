/**
 * The tools a run called, in its thread: each a summary that opens to what it was asked and what
 * it returned. Closed, it says the tool's name, how it is going, and a line of its arguments, or,
 * once it failed or was refused, of why. It follows the run as each call returns.
 */

import type { Artifactr } from "@portalr/client";
import { ChevronRight, Wrench } from "lucide-react";
import type { ReactNode } from "react";
import { CopyButton } from "./copy-button";
import { Icon } from "./icon";
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

/** A part of a call: its name, a way to copy it, and its value, scrolled where it is long. */
function Part({ name, tool, text }: { name: string; tool: string; text: string }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between gap-2">
        <span className={TYPE.note}>{name}</span>
        <CopyButton text={text} what={`the ${name.toLowerCase()} of ${tool}`} />
      </div>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words rounded-md border border-line bg-paper p-3 font-mono text-xs">
        {text}
      </pre>
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
      <details className="group rounded-lg border border-line bg-surface text-sm open:border-edge">
        <summary className="flex min-h-10 cursor-pointer list-none items-center gap-2 rounded-lg px-3 py-2 outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus [&::-webkit-details-marker]:hidden">
          <Icon
            icon={ChevronRight}
            className="size-3.5 shrink-0 text-muted motion-safe:transition-transform group-open:rotate-90 rtl:-scale-x-100 rtl:group-open:rotate-90"
          />
          <Icon icon={Wrench} className="size-3.5 shrink-0 text-muted" />
          <code className="shrink-0 font-mono">{tool.name}</code>
          <span className="min-w-0 flex-1 truncate text-muted text-xs">{line}</span>
          <StatusBadge tone={tone} className="shrink-0">
            {word}
          </StatusBadge>
        </summary>
        <div className="flex flex-col gap-3 border-line border-t p-3">
          <Part name="Arguments" tool={tool.name} text={pretty(tool.args) || "{}"} />
          {tool.status !== "called" && (
            <Part name={returned} tool={tool.name} text={pretty(tool.result)} />
          )}
        </div>
      </details>
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
