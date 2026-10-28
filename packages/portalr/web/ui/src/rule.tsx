/**
 * A reflexr rule, as the pipeline it runs (portalr ADR-0017): its event types, filter, pattern,
 * dedupe and throttle, scope, action, retries and timeout, in that order, in words, with its JSON
 * folded beside it to copy. The same view is a `rule` artifact's in its thread and on its page, a
 * proposed rule's, and a rule's on the Rules page; its revisions and an edit's proposal compare it
 * stage by stage.
 */

import type { Artifactr } from "@portalr/client";
import { createContext, use } from "react";
import { json as asJson, capped, type Data, type Renderer } from "./artifacts";
import { proposedOn } from "./chat";
import { cn } from "./cn";
import { Disclosure } from "./disclosure";
import { isObject } from "./json";
import { JsonView } from "./json-view";
import { type Line, type Stage, stages, stageText } from "./rule-words";
import { TYPE } from "./type";

/** What a rule's preview found, from its proposal's rationale, where it said: "It would have fired 3 times since …". */
const FIRED =
  /It would have fired \d+ times? since \d{4}-\d{2}-\d{2}(?:, among the newest events)?\./;

/**
 * What the preview of `artifact`'s newest accepted proposal found, or null: relayr's `draft_rule`
 * ends its rationale with it. An open one's is said on its card, of what it would make.
 */
export function firedOf(proposals: readonly Artifactr.Proposal[], artifact: string): string | null {
  for (const proposal of [...proposals].reverse()) {
    const found =
      proposal.status === "accept" &&
      proposedOn(proposal) === artifact &&
      FIRED.exec(proposal.rationale ?? "");
    if (found) {
      return found[0];
    }
  }
  return null;
}

/** What the preview of the rule shown found, which its page gives where it knows. */
export const FiredContext = createContext<string | null>(null);

function Lines({ lines, depth = 0 }: { lines: readonly Line[]; depth?: number }) {
  return (
    <ul
      className={cn(
        "m-0 flex min-w-0 list-none flex-col gap-1 p-0",
        depth > 0 && "border-line border-s ps-3",
      )}
    >
      {lines.map((line, at) => (
        <li key={at} className="min-w-0 break-words">
          {line.and && <span className="text-muted">and </span>}
          {line.term !== undefined && <span className="font-mono text-muted">{line.term}: </span>}
          {line.json ? <code className="break-all font-mono text-xs">{line.said}</code> : line.said}
          {line.of && (
            <div className="mt-1">
              <Lines lines={line.of} depth={depth + 1} />
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

/** The stages of a rule, in order, each its name beside what it says. */
export function RulePipeline({ rule }: { rule: Readonly<Record<string, unknown>> }) {
  return (
    <ol
      aria-label="The rule, stage by stage"
      className="m-0 flex list-none flex-col divide-y divide-line rounded-(--card-radius) border border-line bg-surface p-0 text-sm"
    >
      {stages(rule).map((stage: Stage) => (
        <li
          key={stage.name}
          className="flex flex-col gap-x-4 gap-y-0.5 px-(--card-pad) py-2 sm:flex-row"
        >
          <span className={cn(TYPE.labelQuiet, "shrink-0 first-letter:uppercase sm:w-32")}>
            {stage.name}
          </span>
          <div className={cn("min-w-0 flex-1", stage.none ? "text-muted" : "text-fg")}>
            {stage.name === "event types" && !stage.none ? (
              <ul className="m-0 flex list-none flex-wrap gap-1.5 p-0">
                {stage.lines.map((line) => (
                  <li key={line.said}>
                    <code className="break-all rounded-sm bg-wash px-1 font-mono text-xs">
                      {line.said}
                    </code>
                  </li>
                ))}
              </ul>
            ) : (
              <Lines lines={stage.lines} />
            )}
          </div>
        </li>
      ))}
    </ol>
  );
}

/** The stages that can be several lines, compared line by line. */
const LINED = new Set(["event types", "filter", "pattern", "action", "retries", "runs", "more"]);

/** A rule artifact's rule, or null where its data hold none. */
const ruleOf = (data: Data) => (isObject(data.rule) ? data.rule : null);

/** A rule artifact: what its preview found, its pipeline, and its JSON, folded, to copy. */
function RuleArtifact({ data }: { data: Data }) {
  const fired = use(FiredContext);
  const rule = ruleOf(data);
  if (rule === null) {
    return <JsonView data={data} />;
  }
  return (
    <div className="flex min-w-0 flex-col gap-3">
      {fired && <p className="text-fg text-sm">{fired}</p>}
      <RulePipeline rule={rule} />
      <Disclosure summary="The rule, as JSON">
        <JsonView data={rule} name="rule's JSON" />
      </Disclosure>
    </div>
  );
}

/**
 * relayr's `rule` kind, `{rule}`: drawn as its pipeline, titled by its name, and compared stage by
 * stage; data of another shape, as JSON.
 */
export const rule: Renderer = {
  render: (data) => <RuleArtifact data={data} />,
  text: asJson.text,
  title: (data) => {
    const name = ruleOf(data)?.name;
    return typeof name === "string" ? capped(name.slice(0, 400)) : null;
  },
  parts: (data) => {
    const found = ruleOf(data);
    return found === null
      ? (asJson.parts?.(data) ?? [])
      : stages(found).map((stage) => {
          // A stage of lines, as a filter nests, is compared line by line; one line, word by word.
          const lines = LINED.has(stage.name);
          const text = stageText(stage.lines);
          return {
            name: stage.name,
            text: lines ? `${text}\n` : text,
            diff: lines ? "lines" : "words",
          };
        });
  },
  diff: "words",
  inline: true,
};
