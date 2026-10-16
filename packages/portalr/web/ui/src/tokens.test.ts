import { expect, onTestFinished, test } from "vitest";
import { contrast, dark, distance, luminance, token } from "./test/colours";

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

test("a log line's eight colours read as text on the paper and the surface, in each scheme", () => {
  for (const colour of Array.from({ length: 8 }, (_, at) => `ansi-${at}`)) {
    for (const surface of ["paper", "surface"]) {
      expect(
        contrast(token(colour), token(surface)),
        `${colour} on ${surface}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  }
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

const SERIES = ["chart-1", "chart-2", "chart-3"];
const GROUNDS = ["paper", "surface"];
const DEFICIENCIES = ["protanopia", "deuteranopia", "tritanopia"] as const;

/** The series' computed inks, in order, within an element. */
const inks = (within: Element = document.body) => SERIES.map((series) => token(series, within));

/** The least distance between any two of `colours`, as a reader with `deficiency` sees them. */
const closest = (colours: readonly string[], deficiency?: (typeof DEFICIENCIES)[number]) =>
  Math.min(
    ...colours.flatMap((one, at) =>
      colours.slice(at + 1).map((other) => distance(one, other, deficiency)),
    ),
  );

/** An element that asks for colour-blind mode, as a page would on its root. */
function cvd(): HTMLElement {
  const screen = document.createElement("div");
  onTestFinished(() => screen.remove());
  screen.dataset.cvd = "";
  document.body.append(screen);
  return screen;
}

test("a chart's series stand out from the surface, and from the paper, where pages draw them", () => {
  for (const series of SERIES) {
    for (const ground of GROUNDS) {
      expect(
        contrast(token(series), token(ground)),
        `${series} on ${ground}`,
      ).toBeGreaterThanOrEqual(3);
    }
  }
});

test("a chart's series are tints of the brand violet and one accent, led by the violet", () => {
  const [first, second, accent] = SERIES.map((series) => hue(token(series)));
  expect(first).toBeGreaterThanOrEqual(255);
  expect(first).toBeLessThanOrEqual(285);
  expect(second).toBeGreaterThanOrEqual(255);
  expect(second).toBeLessThanOrEqual(285);
  // The one accent is the brand's magenta, which is past every violet.
  expect(accent).toBeGreaterThan(300);
  // The tints differ in lightness, not hue alone.
  expect(Math.abs(luminance(token("chart-1")) - luminance(token("chart-2")))).toBeGreaterThan(0.05);
});

test("a chart's series are told apart, to a reader who sees every colour and to one who sees some", () => {
  expect(closest(inks())).toBeGreaterThanOrEqual(18);
  for (const deficiency of DEFICIENCIES) {
    expect(closest(inks(), deficiency), deficiency).toBeGreaterThanOrEqual(17);
  }
});

test("colour-blind mode swaps the series for others that stand out from the surface and the paper", () => {
  const screen = cvd();
  const swapped = inks(screen);
  expect(swapped).not.toEqual(inks());
  for (const [at, series] of SERIES.entries()) {
    for (const ground of GROUNDS) {
      expect(
        contrast(swapped[at] ?? "", token(ground)),
        `${series} on ${ground}`,
      ).toBeGreaterThanOrEqual(3);
    }
  }
});

test("colour-blind mode's series are told apart even to a reader with a deficiency", () => {
  const swapped = inks(cvd());
  expect(closest(swapped)).toBeGreaterThanOrEqual(18);
  for (const deficiency of DEFICIENCIES) {
    expect(closest(swapped, deficiency), deficiency).toBeGreaterThanOrEqual(17);
  }
});

test("a deficiency is simulated: red and green stay apart on a screen, and merge to a reader without green", () => {
  expect(distance("rgb(200, 0, 0)", "rgb(0, 160, 0)")).toBeGreaterThan(80);
  expect(distance("rgb(200, 0, 0)", "rgb(0, 160, 0)", "deuteranopia")).toBeLessThan(
    distance("rgb(200, 0, 0)", "rgb(0, 160, 0)") / 2,
  );
});

test("by default a series is solid and a line unbroken; colour-blind mode hatches, dashes and reshapes", () => {
  const probe = (within: Element) => {
    const element = document.createElement("span");
    within.append(element);
    const style = getComputedStyle(element);
    const values = [
      "--chart-hatch",
      "--chart-dash-1",
      "--chart-dash-2",
      "--chart-dash-3",
      "--chart-marker-corner-2",
      "--chart-marker-corner-3",
      "--chart-marker-turn-3",
    ].map((property) => style.getPropertyValue(property).trim());
    element.remove();
    return values;
  };
  expect(probe(document.body)).toEqual(["0", "none", "none", "none", "0.5", "0.5", "0deg"]);
  const hatched = getComputedStyle(document.body).getPropertyValue("--chart-hatched").trim();
  expect(Number(hatched)).toBeGreaterThan(0);
  expect(probe(cvd())).toEqual([hatched, "none", "6 4", "2 3", "0", "0", "45deg"]);
});
