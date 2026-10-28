/**
 * The stylesheet leaves out Streamdown's classes for the parts portalr turns off (portalr
 * ADR-0085). The list is global: a class named there is dropped wherever it is written, so none
 * may be one portalr's own code uses: in its scripts, its stylesheets (an `@apply`) or its MDX, as
 * a word of a class list, or in a template literal's text beside a placeholder (`${size} w-8`).
 * Behind a variant it is another class, which Tailwind keeps (`fine:opacity-0` is built while
 * `opacity-0` is left out), so that is no use of it.
 */

import { expect, test } from "vitest";
import styles from "./styles.css?raw";

const sources = import.meta.glob(
  [
    "./**/*.{ts,tsx,css,mdx}",
    "../../app/src/**/*.{ts,tsx,css,mdx}",
    "../../admin/src/**/*.{ts,tsx,css,mdx}",
    // The list itself, which names every one.
    "!./styles.css",
  ],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

/** A class's name, as a regular expression matches it literally. */
const escaped = (name: string) => name.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");

/** Whether `text` writes the class itself: between a list's separators, never behind a variant. */
const usedIn = (name: string, text: string) =>
  new RegExp(`(^|[\\s"'\`{}])${escaped(name)}($|[\\s"'\`$};])`).test(text);

test("a class is found beside a template's placeholder and in an @apply, and not behind a variant", () => {
  expect(usedIn("bg-primary", 'className="hover:bg-primary"')).toBe(false);
  expect(usedIn("w-8", "`${size} w-8`")).toBe(true);
  expect(usedIn("w-8", "`w-8${size}`")).toBe(true);
  expect(usedIn("shadow-lg", "  @apply shadow-lg;")).toBe(true);
  expect(usedIn("w-8", 'className="w-80"')).toBe(false);
});

test("no class the stylesheet leaves out is one portalr's own code writes", () => {
  const listed = /@source not inline\("([^"]+)"\)/.exec(styles)?.[1]?.split(/\s+/) ?? [];
  expect(listed.length).toBeGreaterThan(0);
  const used = Object.entries(sources)
    .filter(([path]) => !/\.test\.tsx?$/.test(path))
    .flatMap(([path, text]) =>
      listed.filter((name) => usedIn(name, text)).map((name) => `${path}: ${name}`),
    );
  expect(used).toEqual([]);
});
