/**
 * Artifacts' titles, from their data through their kind's renderer, for the places that name an
 * artifact: its id is a fallback, never the first choice (portalr ADR-0029).
 */

import { type Data, type Renderers, rendererFor } from "@portalr/ui";
import { RENDERERS } from "./renderers";

const isData = (value: unknown): value is Data =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** An artifact's title, or null where its data hold none. */
export const titleOf = (kind: string, data: unknown, renderers: Renderers = RENDERERS) =>
  isData(data) ? rendererFor(kind, renderers).title(data) : null;

/**
 * The titles of the artifacts artifactr lists, by id. What the list holds that isn't an artifact
 * with an id, a kind and data is skipped: it is read as a list, which it is trusted to be, not
 * validated.
 */
export function titlesOf(listed: unknown, renderers: Renderers = RENDERERS): Map<string, string> {
  const titles = new Map<string, string>();
  if (!Array.isArray(listed)) {
    return titles;
  }
  for (const each of listed as unknown[]) {
    if (isData(each) && typeof each.id === "string" && typeof each.kind === "string") {
      const title = titleOf(each.kind, each.data, renderers);
      if (title !== null) {
        titles.set(each.id, title);
      }
    }
  }
  return titles;
}
