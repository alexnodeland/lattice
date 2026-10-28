/**
 * The stylesheet leaves out Streamdown's classes for the parts portalr turns off (portalr
 * ADR-0085). The list is global: a class named there is dropped wherever it is written, so none
 * may be one portalr's own code uses.
 */

import { expect, test } from "vitest";
import styles from "./styles.css?raw";

const sources = import.meta.glob(
  ["./**/*.{ts,tsx}", "../../app/src/**/*.{ts,tsx}", "../../admin/src/**/*.{ts,tsx}"],
  { query: "?raw", import: "default", eager: true },
) as Record<string, string>;

/** A class's name, as a regular expression matches it literally. */
const escaped = (name: string) => name.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");

test("no class the stylesheet leaves out is one portalr's own code writes", () => {
  const listed = /@source not inline\("([^"]+)"\)/.exec(styles)?.[1]?.split(/\s+/) ?? [];
  expect(listed.length).toBeGreaterThan(0);
  const used = Object.entries(sources)
    .filter(([path]) => !/\.test\.tsx?$/.test(path))
    .flatMap(([path, text]) =>
      listed
        .filter((name) => new RegExp(`(^|[\\s"'\`])${escaped(name)}($|[\\s"'\`])`).test(text))
        .map((name) => `${path}: ${name}`),
    );
  expect(used).toEqual([]);
});
