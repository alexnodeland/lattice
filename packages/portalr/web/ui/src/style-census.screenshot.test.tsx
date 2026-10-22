/**
 * The style census (lattice RFC-0007): how many distinct looks the galleries' links, buttons and
 * headings have, at rest. The polish pass put each on the kit's few variants, so it now fails
 * unless the count is exactly what `LOOKS` accounts for: a ratchet, lowered as looks are folded
 * together, and raised only with the kit (portalr ADR-0066). Run with the screenshot suites.
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
 * Every look the galleries have, by kind, in light and dark alike: what the census counts must be
 * exactly as many, so a look that goes and another that comes are both seen. Folding two looks
 * together removes a line here; a new one comes only with a new kit variant, named here. The lines
 * account for the count; they aren't matched one by one to the looks' signatures.
 */
const LOOKS = {
  links: [
    "the skip link",
    "the header's home (the mark)",
    "a nav link",
    "the current nav link",
    "a tab",
    "the current tab",
    "TextLink default, in body text",
    "TextLink subtle, in body text",
    "TextLink subtle, in small text (a breadcrumb)",
    "TextLink nav",
    "a row's link (subtle, semibold)",
    "a test gallery's raw link (the Sheet's Usage), not a product look",
  ],
  buttons: [
    "the header's Menu",
    "the header's switcher",
    "the header's account menu",
    "Button primary",
    "Button secondary",
    "Button ghost",
    "Button danger",
    "Button danger-soft",
    "Button disabled",
    "Button pressed (a toggle on)",
    "Button primary, small",
    "Button secondary, small",
    "Button ghost, small",
    "Button danger, small",
    "Button danger-soft, small",
    "Button disabled, small",
    "IconButton ghost",
    "IconButton pressed",
    "a select's trigger",
    "a select's trigger, disabled",
    "a disclosure's trigger",
  ],
  headings: ["the page's (h1)", "a section's", "a label's"],
} as const;

test("the census of links, buttons and headings: exactly the looks the kit has", async ({
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
    const most = LOOKS[kind].length;
    const said =
      seen.size < most
        ? `${kind}: fewer looks than the ceiling: lower LOOKS.${kind} to ${seen.size}`
        : `${kind}: more looks than the ceiling: raise it only if the kit gained a variant, and name it in LOOKS.${kind}`;
    expect(seen.size, `${said}\n${[...seen].join("\n")}`).toBe(most);
  }
});
