/**
 * GitHub's callouts: a quote whose first line is `[!NOTE]`, `[!TIP]`, `[!IMPORTANT]`, `[!WARNING]`
 * or `[!CAUTION]`, as models write them. A remark step marks each one as an `aside` with its kind,
 * which `Markdown` lets through its sanitizer and renders as an `Alert` (portalr ADR-0043).
 */

import type { Blockquote, Nodes, Root } from "mdast";

/** The kinds of callout, as GitHub names them. */
export const CALLOUTS = ["note", "tip", "important", "warning", "caution"] as const;

export type Callout = (typeof CALLOUTS)[number];

/** The marker, alone on the quote's first line, in any case. */
const MARKER = new RegExp(`^\\[!(${CALLOUTS.join("|")})\\][^\\S\\n]*(?:\\n|$)`, "i");

/** Whether `kind` names a callout. */
export function isCallout(kind: unknown): kind is Callout {
  return (CALLOUTS as readonly unknown[]).includes(kind);
}

/** Mark a quote that opens with a marker as a callout of its kind, and drop the marker. */
function mark(quote: Blockquote): void {
  const first = quote.children[0];
  const text = first?.type === "paragraph" ? first.children[0] : undefined;
  if (first?.type !== "paragraph" || text?.type !== "text") {
    return;
  }
  const found = MARKER.exec(text.value);
  const kind = found?.[1]?.toLowerCase() ?? "";
  if (!(found && isCallout(kind))) {
    return;
  }
  text.value = text.value.slice(found[0].length);
  if (!text.value) {
    first.children.shift();
  }
  if (first.children.length === 0) {
    quote.children.shift();
  }
  quote.data = { hName: "aside", hProperties: { dataCallout: kind } };
}

function walk(node: Nodes): void {
  if (node.type === "blockquote") {
    mark(node);
  }
  if ("children" in node) {
    for (const child of node.children) {
      walk(child);
    }
  }
}

/** The remark plugin: every callout in the tree, however deep. */
export function remarkCallouts() {
  return (tree: Root) => walk(tree);
}
