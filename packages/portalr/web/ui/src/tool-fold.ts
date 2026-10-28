/**
 * What a run's calls did, in plain words (portalr ADR-0053): the first of four levels a thread
 * shows them at, each a tap deeper and none required: this line ("Made an app, read 2
 * artifacts"), the calls one by one (a verb and a line of what each was about), a call's detail
 * (what it was asked and what it returned), and the raw form. Tool ids and JSON wait for the last
 * two; the phone's sheet and the desktop's unfurl share these words.
 */

import type { Artifactr } from "@portalr/client";

/**
 * The tools a thread's runs call, artifactr's and its connected apps': each tool's name, what it
 * did and what it acted on, one of it. Many is the one's "a" or "an" as their count and a plural
 * "s"; doing is the verb's "ed" as "ing", but for the few in IRREGULAR.
 */
const PHRASES = new Map(
  [
    "create_app|Made|an app",
    "update_app|Updated|an app",
    "create_artifact|Made|an artifact",
    "edit_artifact|Edited|an artifact",
    "read_artifact|Read|an artifact",
    "archive_artifact|Archived|an artifact",
    "list_artifacts|Looked through|the artifacts",
    "draw|Drew|a diagram",
    "draw_mermaid|Drew|a diagram",
    "edit_elements|Edited|a diagram",
    "read_diagram|Read|a diagram",
    "view_diagram|Looked at|a diagram",
    "read_native|Read|a file",
    "edit_native|Edited|a file",
    "edit_text|Edited|an artifact",
    "draft_rule|Drafted|a rule",
    "view_page|Looked at|a page",
    "find_commands|Looked up|commands",
    "read_events|Read|the events",
    "read_review|Read|a review",
    "post_notice|Posted|a notice",
    "send_message|Sent|a message",
    "create_thread|Started|a thread",
    "read_item|Read|an item",
    "file_item|Filed|an item",
    "set_item_state|Updated|an item",
    "comment_on_item|Commented on|an item",
  ].map((line) => {
    const [name = "", done = "", one = ""] = line.split("|");
    return [name, [done, one] as Phrase] as const;
  }),
);

/** What a tool did and what it acted on, one of it. */
type Phrase = readonly [done: string, one: string];

/** A tool no table names: a tool, in plain words. */
const TOOL: Phrase = ["Used", "a tool"];

/** The verbs whose doing isn't their "ed" as "ing". */
const IRREGULAR: Readonly<Record<string, string>> = {
  Made: "Making",
  Read: "Reading",
  Drew: "Drawing",
  Sent: "Sending",
};

const phrase = (name: string): Phrase => PHRASES.get(name) ?? TOOL;

const doing = (done: string) =>
  done.replace(/^\w+/, (verb) => IRREGULAR[verb] ?? verb.replace(/e?d$/, "ing"));

const object = ([, one]: Phrase, n: number) =>
  n === 1 ? one : one.replace(/^an? (.*)/, `${n} $1s`);

/** Whether a call failed, or was refused. */
const failed = (tool: Artifactr.Tool) => tool.status === "error" || tool.status === "retry";

/** One call, as its row says it: "Made an app", or "Making an app" while it runs. */
export function callLabel(tool: Artifactr.Tool): string {
  const said = phrase(tool.name);
  return `${tool.status === "called" ? doing(said[0]) : said[0]} ${said[1]}`;
}

/**
 * The calls together, done: each tool's verb and its count, in the order first called, so
 * "Made an app, read 2 artifacts"; tools no table names are one "used 3 tools".
 */
export function doneLabel(tools: readonly Artifactr.Tool[]): string {
  // By their words, so two tools that say the same, as draw and draw_mermaid do, are one.
  const counts = new Map<string, [Phrase, number]>();
  for (const tool of tools) {
    const said = phrase(tool.name);
    const key = said.join("|");
    counts.set(key, [said, (counts.get(key)?.[1] ?? 0) + 1]);
  }
  const parts = [...counts.values()].map(([said, n]) => `${said[0]} ${object(said, n)}`);
  const joined = parts.join(", ");
  return joined.charAt(0) + joined.slice(1).toLowerCase();
}

/**
 * The plain parts of a group's line: what it says, how many failed, and whether it runs: while a
 * call does, or its run does, between one call's answer and the next, it says what it is doing.
 */
export function foldSummary(tools: readonly Artifactr.Tool[], runRunning = false) {
  const latest = tools.findLast((tool) => tool.status === "called") ?? tools.at(-1);
  const running = runRunning || tools.some((tool) => tool.status === "called");
  return {
    label:
      running && latest
        ? `${doing(phrase(latest.name)[0])} ${phrase(latest.name)[1]}…`
        : doneLabel(tools),
    failed: tools.filter(failed).length,
    running,
  };
}

/** Where a value holds what a call was about, the first of these keys a string has. */
const ABOUT = ["title", "name", "query", "url", "path"];

/**
 * A line of what a call was about, in plain words where its arguments give one (a title, a
 * name), or why it failed; else nothing, so no JSON shows at the second level.
 */
export function callAbout(tool: Artifactr.Tool): string {
  if (failed(tool)) {
    return tool.result.replace(/\s+/g, " ").trim();
  }
  try {
    const args: unknown = JSON.parse(tool.args);
    if (args && typeof args === "object") {
      const values = args as Record<string, unknown>;
      const found = ABOUT.map((key) => values[key]).find((value) => typeof value === "string");
      return typeof found === "string" ? found : "";
    }
  } catch {
    // A value cut short, or not JSON: nothing plain to say.
  }
  return "";
}
