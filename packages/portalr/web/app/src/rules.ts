/**
 * A stored rule as a person writes it: reflexr's JSON, read here only far enough to send.
 *
 * reflexr checks the rule, and its answer is what the field shows: the browser doesn't hold
 * reflexr's limits, which an application sets (portalr ADR-0020).
 */

import type { ReflexrApi } from "@portalr/client";

type Rule = ReflexrApi.components["schemas"]["Rule-Input"];

/**
 * A new rule's starting text: what every stored rule needs, for the person to name and fill.
 * The name's namespace, and the action, must be ones the application lets stored rules use.
 */
export const SKELETON = `{
  "name": "",
  "description": "",
  "when": {
    "filter": { "kind": "on", "types": [] },
    "throttle": { "at_most": 10, "per": "PT1H" }
  },
  "then": { "action": "" },
  "ordering": "none",
  "timeout": "PT30S"
}
`;

/** A rule's text as JSON, or why it isn't. reflexr says whether it's a rule. */
export function read(text: string): { rule: Rule } | { refused: string } {
  try {
    return { rule: JSON.parse(text) };
  } catch (error) {
    return { refused: `That isn't JSON: ${error instanceof Error ? error.message : error}.` };
  }
}
