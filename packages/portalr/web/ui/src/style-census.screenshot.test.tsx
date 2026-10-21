/**
 * The style census (lattice RFC-0007): how many distinct looks the galleries' links, buttons and
 * headings have, at rest. It reports, and fails nothing, until the polish pass has put each on the
 * kit's few variants; then it fails on more than the kit has. Run with the screenshot suites.
 */

import { test } from "vitest";
import { render } from "vitest-browser-react";
import { AdminGallery, Controls, Gallery, Kit, Sheet, Thread } from "./test/galleries";

/** What tells one look from another: colour, type, decoration, fill, edge, corners and padding. */
const SIGNATURE = [
  "color",
  "font-size",
  "font-weight",
  "text-decoration-line",
  "background-color",
  "border-top-width",
  "border-top-color",
  "border-top-left-radius",
  "padding-top",
  "padding-left",
] as const;

const KINDS = {
  links: "a[href]",
  buttons: "button, [role='button']",
  headings: "h1, h2, h3, h4, h5, h6",
} as const;

test("the census of links, buttons and headings, reported", async ({ annotate }) => {
  const looks = Object.fromEntries(
    Object.keys(KINDS).map((kind) => [kind, new Set<string>()]),
  ) as Record<keyof typeof KINDS, Set<string>>;
  const scenes = [Gallery, AdminGallery, Controls, Kit, Thread, Sheet];
  for (const Scene of scenes) {
    const screen = await render(<Scene />);
    for (const [kind, selector] of Object.entries(KINDS) as [keyof typeof KINDS, string][]) {
      for (const element of document.body.querySelectorAll(selector)) {
        const style = getComputedStyle(element);
        looks[kind].add(SIGNATURE.map((property) => style.getPropertyValue(property)).join(" | "));
      }
    }
    await screen.unmount();
  }
  const report = Object.entries(looks)
    .map(([kind, seen]) => `${kind}: ${seen.size} distinct looks`)
    .join("; ");
  await annotate(`style census: ${report}`);
  console.info(`style census: ${report}`);
});
