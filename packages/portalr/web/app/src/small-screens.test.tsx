/**
 * The app's own routes on a phone and a tablet (portalr ADR-0082): at 320, 360, 390, 430 and 768
 * nothing is wider than the page; what would be scrolls inside its own box.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page } from "vitest/browser";
import { open } from "./test/app";
import { serve, WORLD } from "./test/notes";

afterEach(() => vi.unstubAllGlobals());

/** What scrolls inside its own box may be wider than the page; the page itself never is. */
function wider(): string[] {
  const scrolls = (element: Element | null): boolean =>
    element !== null &&
    element !== document.body &&
    (/auto|scroll/.test(getComputedStyle(element).overflowX) || scrolls(element.parentElement));
  return Array.from(document.body.querySelectorAll<HTMLElement>("*"))
    .filter(
      (element) =>
        element.getBoundingClientRect().right > window.innerWidth + 1 &&
        !scrolls(element.parentElement),
    )
    .map(
      (element) => `${element.tagName.toLowerCase()}.${element.className.toString().slice(0, 60)}`,
    );
}

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
        await expect.element(screen.getByText(words, { exact: false }).first()).toBeVisible();
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
