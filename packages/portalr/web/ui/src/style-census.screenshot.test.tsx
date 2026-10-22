/**
 * The style census (lattice RFC-0007): how many distinct looks the galleries' links, buttons and
 * headings have, at rest. The polish pass put each on the kit's few variants, so it now fails on a
 * look past what the kit has (`MOST`): a ratchet, lowered as looks are folded together, and raised
 * only with the kit (portalr ADR-0066). Run with the screenshot suites.
 */

import { expect, test } from "vitest";
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

/**
 * The looks the kit has, in light and dark alike. Links: a text link's three variants at the sizes
 * they inherit, the nav's link and its current one, the header's home, a tab and the current tab,
 * a row's link, and the skip link. Buttons: the button's variants at both sizes and disabled, an
 * icon button, the header's three triggers, a select's trigger and its placeholder, a pressed
 * toggle, and a disclosure. Headings: the page's, a section's, and a label's.
 */
const MOST = { links: 12, buttons: 21, headings: 3 } as const;

test("the census of links, buttons and headings: no more looks than the kit has", async ({
  annotate,
}) => {
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
  for (const [kind, seen] of Object.entries(looks) as [keyof typeof KINDS, Set<string>][]) {
    expect(seen.size, `${kind}: ${[...seen].join("\n")}`).toBeLessThanOrEqual(MOST[kind]);
  }
});
