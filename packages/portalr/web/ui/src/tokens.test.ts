import { expect, onTestFinished, test } from "vitest";
import { contrast, dark, luminance, token } from "./test/colours";

test("the working colour is the scheme's violet", () => {
  expect(token("accent")).toBe(dark ? "rgb(226, 204, 245)" : "rgb(107, 47, 160)");
});

test("text is readable on every surface, and on the working colour", () => {
  for (const surface of ["paper", "surface"]) {
    expect(contrast(token("fg"), token(surface))).toBeGreaterThanOrEqual(7);
    expect(contrast(token("muted"), token(surface))).toBeGreaterThanOrEqual(4.5);
    expect(contrast(token("accent"), token(surface))).toBeGreaterThanOrEqual(4.5);
  }
  expect(contrast(token("on-accent"), token("accent"))).toBeGreaterThanOrEqual(4.5);
});

test("the focus ring stands out from every surface", () => {
  for (const surface of ["paper", "surface"]) {
    expect(contrast(token("focus"), token(surface))).toBeGreaterThanOrEqual(3);
  }
});

/** A colour's hue, in degrees, from its `rgb(r, g, b)`. */
function hue(rgb: string): number {
  const [r = 0, g = 0, b = 0] = (rgb.match(/\d+/g) ?? []).map((part) => Number(part) / 255);
  const top = Math.max(r, g, b);
  const spread = top - Math.min(r, g, b);
  if (spread === 0) {
    return 0;
  }
  const sector =
    top === r ? ((g - b) / spread) % 6 : top === g ? (b - r) / spread + 2 : (r - g) / spread + 4;
  return (sector * 60 + 360) % 360;
}

// Each scheme's project runs this once, so it holds in both: violet's hue, not the cyan the dark
// scheme once had (190°), nor the magenta and pink (300° and over) that are the other inks.
test("the focus ring is violet in this scheme", () => {
  const violet = hue(token("focus"));
  expect(violet).toBeGreaterThanOrEqual(255);
  expect(violet).toBeLessThanOrEqual(285);
});

test("a surface is raised: lighter than the paper, in both schemes", () => {
  expect(luminance(token("surface"))).toBeGreaterThan(luminance(token("paper")));
});

test("a control's boundary stands out from every surface, and from the wash", () => {
  for (const surface of ["paper", "surface", "wash"]) {
    expect(contrast(token("edge"), token(surface))).toBeGreaterThanOrEqual(3);
  }
});

test("text and the focus ring read on the wash", () => {
  expect(contrast(token("fg"), token("wash"))).toBeGreaterThanOrEqual(7);
  expect(contrast(token("muted"), token("wash"))).toBeGreaterThanOrEqual(4.5);
  expect(contrast(token("accent"), token("wash"))).toBeGreaterThanOrEqual(4.5);
  expect(contrast(token("focus"), token("wash"))).toBeGreaterThanOrEqual(3);
});

test("the danger colour reads on every surface, and its words read on it, hovered or not", () => {
  for (const surface of ["paper", "surface", "wash"]) {
    expect(contrast(token("danger"), token(surface))).toBeGreaterThanOrEqual(4.5);
  }
  expect(contrast(token("on-danger"), token("danger"))).toBeGreaterThanOrEqual(4.5);
  expect(token("danger-hover")).not.toBe(token("danger"));
  expect(contrast(token("on-danger"), token("danger-hover"))).toBeGreaterThanOrEqual(4.5);
});

test("the hovered working colour keeps its text readable", () => {
  expect(token("accent-hover")).not.toBe(token("accent"));
  expect(contrast(token("on-accent"), token("accent-hover"))).toBeGreaterThanOrEqual(4.5);
});

test("a screen that re-skins the working colour re-mixes the wash and the hover from it", () => {
  const screen = document.createElement("div");
  onTestFinished(() => screen.remove());
  screen.dataset.brand = "grantr";
  screen.style.setProperty("--accent", dark ? "#fff6d6" : "#6b5300");
  document.body.append(screen);
  expect(token("wash", screen)).not.toBe(token("wash"));
  expect(token("accent-hover", screen)).not.toBe(token("accent-hover"));
  expect(contrast(token("fg", screen), token("wash", screen))).toBeGreaterThanOrEqual(7);
  expect(contrast(token("accent", screen), token("wash", screen))).toBeGreaterThanOrEqual(4.5);
  expect(
    contrast(token("on-accent", screen), token("accent-hover", screen)),
  ).toBeGreaterThanOrEqual(4.5);
});

test("a page asks for a scheme with data-theme", () => {
  const html = document.documentElement;
  onTestFinished(() => {
    delete html.dataset.theme;
  });
  html.dataset.theme = dark ? "light" : "dark";
  expect(token("accent")).toBe(dark ? "rgb(107, 47, 160)" : "rgb(226, 204, 245)");
});

test("a chart's series stand out from the surface, and from the paper, where pages draw them", () => {
  for (const series of ["chart-1", "chart-2", "chart-3"]) {
    for (const ground of ["surface", "paper"]) {
      expect(
        contrast(token(series), token(ground)),
        `${series} on ${ground}`,
      ).toBeGreaterThanOrEqual(3);
    }
  }
});
