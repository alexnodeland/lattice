import { expect, test } from "vitest";
import { contrast, dark, token } from "./test/colours";

test("the working colour is the scheme's violet", () => {
  expect(token("accent")).toBe(dark ? "rgb(226, 204, 245)" : "rgb(107, 47, 160)");
});

test("text is readable on every surface, and on the working colour", () => {
  for (const surface of ["paper", "surface"]) {
    expect(contrast(token("text"), token(surface))).toBeGreaterThanOrEqual(7);
    expect(contrast(token("graphite"), token(surface))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("accent"), token(surface))).toBeGreaterThanOrEqual(4.5);
  }
  expect(contrast(token("on-accent"), token("accent"))).toBeGreaterThanOrEqual(4.5);
});

test("a page asks for a scheme with data-theme", () => {
  document.documentElement.dataset.theme = dark ? "light" : "dark";
  expect(token("accent")).toBe(dark ? "rgb(107, 47, 160)" : "rgb(226, 204, 245)");
  delete document.documentElement.dataset.theme;
});
