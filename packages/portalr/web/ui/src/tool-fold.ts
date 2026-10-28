/**
 * What a run's calls did, in plain words (portalr ADR-0055): the first of four levels a thread
 * shows them at, each a tap deeper and none required: this line ("Made an app, read 2
 * artifacts"), the calls one by one (a verb and a line of what each was about), a call's detail
 * (what it was asked and what it returned), and the raw form. Tool ids and JSON wait for the last
 * two; the phone's sheet and the desktop's unfurl share these words.
 */

import type { Artifactr } from "@portalr/client";

/** A tool's verb, done and doing, and what it acted on: one, and many as `N`. */
type Phrase = readonly [done: string, doing: string, one: string, many: string];

const artifact = ["an artifact", "N artifacts"] as const;
const diagram = ["a diagram", "N diagrams"] as const;
const file = ["a file", "N files"] as const;
const item = ["an item", "N items"] as const;
const page = ["a page", "N pages"] as const;

/** The tools a thread's runs call, artifactr's and its connected apps', by name. */
const PHRASES: Readonly<Record<string, Phrase>> = {
  create_app: ["Made", "Making", "an app", "N apps"],
  update_app: ["Updated", "Updating", "an app", "N apps"],
  create_artifact: ["Made", "Making", ...artifact],
  edit_artifact: ["Edited", "Editing", ...artifact],
  read_artifact: ["Read", "Reading", ...artifact],
  archive_artifact: ["Archived", "Archiving", ...artifact],
  list_artifacts: ["Looked through", "Looking through", "the artifacts", "the artifacts"],
  draw: ["Drew", "Drawing", ...diagram],
  draw_mermaid: ["Drew", "Drawing", ...diagram],
  edit_elements: ["Edited", "Editing", ...diagram],
  read_diagram: ["Read", "Reading", ...diagram],
  view_diagram: ["Looked at", "Looking at", ...diagram],
  read_native: ["Read", "Reading", ...file],
  edit_native: ["Edited", "Editing", ...file],
  edit_text: ["Edited", "Editing", ...file],
  draft_document: ["Drafted", "Drafting", "a document", "N documents"],
  draft_rule: ["Drafted", "Drafting", "a rule", "N rules"],
  draft: ["Wrote", "Writing", "a draft", "N drafts"],
  fetch: ["Fetched", "Fetching", ...page],
  view_page: ["Looked at", "Looking at", ...page],
  find_commands: ["Looked up", "Looking up", "commands", "commands"],
  read_events: ["Read", "Reading", "the events", "the events"],
  read_review: ["Read", "Reading", "a review", "N reviews"],
  post_notice: ["Posted", "Posting", "a notice", "N notices"],
  send_message: ["Sent", "Sending", "a message", "N messages"],
  create_thread: ["Started", "Starting", "a thread", "N threads"],
  read_item: ["Read", "Reading", ...item],
  file_item: ["Filed", "Filing", ...item],
  set_item_state: ["Updated", "Updating", ...item],
  comment_on_item: ["Commented on", "Commenting on", ...item],
  publish: ["Published", "Publishing", "it", "it"],
};

/** A tool no table names: a tool, in plain words. */
const TOOL: Phrase = ["Used", "Using", "a tool", "N tools"];

const phrase = (name: string): Phrase => PHRASES[name] ?? TOOL;

const object = ([, , one, many]: Phrase, n: number) =>
  n === 1 ? one : many.replace("N", String(n));

/** Whether a call failed, or was refused. */
const failed = (tool: Artifactr.Tool) => tool.status === "error" || tool.status === "retry";

/** One call, as its row says it: "Made an app", or "Making an app" while it runs. */
export function callLabel(tool: Artifactr.Tool): string {
  const said = phrase(tool.name);
  return `${tool.status === "called" ? said[1] : said[0]} ${said[2]}`.trimEnd();
}

/**
 * The calls together, done: each tool's verb and its count, in the order first called, so
 * "Made an app, read 2 artifacts"; tools no table names are one "used 3 tools".
 */
export function doneLabel(tools: readonly Artifactr.Tool[]): string {
  const counts = new Map<Phrase, number>();
  for (const tool of tools) {
    const said = phrase(tool.name);
    counts.set(said, (counts.get(said) ?? 0) + 1);
  }
  const parts = [...counts].map(([said, n]) => `${said[0]} ${object(said, n)}`);
  const joined = parts.join(", ");
  return joined.charAt(0) + joined.slice(1).toLowerCase();
}

/** The plain parts of a group's line: what it says, how many failed, and whether one runs. */
export function foldSummary(tools: readonly Artifactr.Tool[]) {
  const running = tools.findLast((tool) => tool.status === "called");
  return {
    label: running ? `${callLabel(running)}…` : doneLabel(tools),
    failed: tools.filter(failed).length,
    running: running !== undefined,
  };
}

/** Where a value holds what a call was about, the first of these keys a string has. */
const ABOUT = ["title", "name", "description", "query", "url", "path", "kind", "id"];

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
