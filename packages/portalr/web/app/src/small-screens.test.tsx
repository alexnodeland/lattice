/**
 * The app's own routes on a phone and a tablet (portalr ADR-0082): at 320, 360, 390, 430 and 768
 * nothing is wider than the page; what would be scrolls inside its own box.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open } from "./test/app";
import { serve, WORLD } from "./test/notes";
import { wider } from "./test/overflow";
import * as rules from "./test/rules";

afterEach(() => vi.unstubAllGlobals());

const WIDTHS = [320, 360, 390, 430, 768];
const ROUTES: [string, string, string[], boolean?][] = [
  ["the threads list", "/t/acme/w/notes", ["Waiting for you"]],
  [
    "a thread with a question",
    "/t/acme/w/notes/threads/thr_1",
    ["Which week should the note cover?"],
  ],
  ["an artifact", "/t/acme/w/notes/artifacts/note_1", ["Ship on"]],
  ["the sign-in page", "/sign-in", ["Sign in"], true],
];
for (const [what, path, seen, signedOut] of ROUTES) {
  for (const width of WIDTHS) {
    test(`${what} at ${width}px is never wider than the page`, async () => {
      await page.viewport(width, 900);
      const { screen } = await open(path, serve, () => null, {
        ...WORLD,
        signedOut: signedOut ?? false,
      });
      for (const words of seen) {
        // The first one shown: the threads are a table on a wide page and rows on a narrow one.
        await expect
          .poll(() =>
            screen
              .getByText(words, { exact: false })
              .elements()
              .some((element) => element.checkVisibility()),
          )
          .toBe(true);
      }
      const found = wider();
      expect(found, found.join("\n")).toEqual([]);
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
    });
  }
}

// A rule drafted in a thread, and its page: the pipeline, an edit's changes, and the JSON opened.
const RULES: [string, string, string][] = [
  ["a thread with a rule and an edit of it", "/t/acme/w/notes/threads/thr_r", "The rule, as JSON"],
  ["a rule's page", "/t/acme/w/notes/artifacts/rule_1", "The rule, as JSON"],
  ["the proposals, a rule's among them", "/t/acme/w/notes/proposals", ""],
];
for (const [what, path, fold] of RULES) {
  for (const width of WIDTHS) {
    test(`${what} at ${width}px is never wider than the page`, async () => {
      await page.viewport(width, 900);
      const { screen } = await open(path, rules.serve, () => null, rules.WORLD);
      if (fold) {
        await screen.getByRole("button", { name: fold }).first().click();
        await expect.element(screen.getByText("per service").first()).toBeVisible();
      } else {
        await expect.element(screen.getByText("Couldn't work out", { exact: false })).toBeVisible();
      }
      const found = wider();
      expect(found, found.join("\n")).toEqual([]);
      expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
    });
  }
}

test("a thread at 200% text is never wider than the page", async () => {
  // The text doubled, as a reader's zoom doubles it (WCAG 1.4.4); the reflow at 320px (1.4.10) is
  // the 320px case above.
  await page.viewport(390, 900);
  document.documentElement.style.fontSize = "200%";
  try {
    const { screen } = await open("/t/acme/w/notes/threads/thr_1", serve, () => null, WORLD);
    await expect
      .element(screen.getByText("Which week should the note cover?").first())
      .toBeVisible();
    const found = wider();
    expect(found, found.join("\n")).toEqual([]);
    expect(document.documentElement.scrollWidth).toBeLessThanOrEqual(window.innerWidth);
  } finally {
    document.documentElement.style.removeProperty("font-size");
  }
});
