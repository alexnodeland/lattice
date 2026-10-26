import { expect, onTestFinished, test } from "vitest";
import { commands } from "vitest/browser";
import { contrast, dark, deltaE2000, distance, luminance, token } from "./test/colours";

test("the working colour is the scheme's violet", () => {
  expect(token("accent")).toBe(dark ? "rgb(217, 191, 243)" : "rgb(107, 47, 160)");
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

test("selected text reads on the selection, which is told from the paper", () => {
  expect(contrast(token("fg"), token("selection"))).toBeGreaterThanOrEqual(7);
  expect(contrast(token("selection"), token("paper"))).toBeGreaterThanOrEqual(1.5);
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
  expect(token("accent")).toBe(dark ? "rgb(107, 47, 160)" : "rgb(217, 191, 243)");
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
  // The one accent is a teal: well clear of the violets, and of the danger colour's red.
  expect(accent).toBeGreaterThanOrEqual(150);
  expect(accent).toBeLessThanOrEqual(200);
  // The tints differ in lightness, not hue alone.
  expect(Math.abs(luminance(token("chart-1")) - luminance(token("chart-2")))).toBeGreaterThan(0.05);
});

/**
 * The least CIEDE2000 distance two series may be apart: 20, where 1 is the least a person sees and
 * a few are plainly different colours. It is the floor ADR-0036 holds, to a reader who sees every
 * colour and, simulated, to one with protanopia, deuteranopia or tritanopia.
 */
const APART = 20;

test("a chart's series are told apart, to a reader who sees every colour and to one who sees some", () => {
  expect(closest(inks())).toBeGreaterThanOrEqual(APART);
  for (const deficiency of DEFICIENCIES) {
    expect(closest(inks(), deficiency), deficiency).toBeGreaterThanOrEqual(APART);
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
  expect(closest(swapped)).toBeGreaterThanOrEqual(APART);
  for (const deficiency of DEFICIENCIES) {
    expect(closest(swapped, deficiency), deficiency).toBeGreaterThanOrEqual(APART);
  }
});

/** Highlighting's colours, which `tokens.css` sets for its theme (portalr ADR-0044). */
const CODE = [
  "code-foreground",
  "code-token-keyword",
  "code-token-link",
  "code-token-string",
  "code-token-string-expression",
  "code-token-function",
  "code-token-constant",
  "code-token-parameter",
  "code-token-punctuation",
  "code-token-comment",
] as const;

test("code's colours read as text on the paper and the surface, by default and in colour-blind mode", () => {
  for (const within of [document.body, cvd()]) {
    for (const colour of CODE) {
      for (const surface of ["paper", "surface"]) {
        expect(
          contrast(token(colour, within), token(surface, within)),
          `${colour} on ${surface}${within === document.body ? "" : ", colour-blind"}`,
        ).toBeGreaterThanOrEqual(4.5);
      }
    }
  }
});

test("colour-blind mode's code inks, keywords, strings and the rest, are told apart by every reader", () => {
  const screen = cvd();
  const inked = ["code-token-keyword", "code-token-string", "code-token-function"].map((colour) =>
    token(colour, screen),
  );
  expect(closest(inked)).toBeGreaterThanOrEqual(APART);
  for (const deficiency of DEFICIENCIES) {
    expect(closest(inked, deficiency), deficiency).toBeGreaterThanOrEqual(APART);
  }
});

test("CIEDE2000 gives Sharma, Wu and Dalal's published values", () => {
  expect(deltaE2000([50, 2.6772, -79.7751], [50, 0, -82.7485])).toBeCloseTo(2.0425, 3);
  expect(deltaE2000([50, 2.5, 0], [73, 25, -18])).toBeCloseTo(27.1492, 3);
  expect(deltaE2000([60.2574, -34.0099, 36.2677], [60.4626, -34.1751, 39.4387])).toBeCloseTo(
    1.2644,
    3,
  );
});

test("greys stay grey to every deficiency, which only moves the colours", () => {
  for (const deficiency of DEFICIENCIES) {
    expect(distance("rgb(128, 128, 128)", "rgb(128, 128, 128)", deficiency)).toBeCloseTo(0, 1);
    // A grey and its simulation are the same grey: it sits as far from black as ever.
    expect(distance("rgb(128, 128, 128)", "rgb(0, 0, 0)", deficiency)).toBeCloseTo(
      distance("rgb(128, 128, 128)", "rgb(0, 0, 0)"),
      0,
    );
  }
});

test("a colour that isn't opaque sRGB is refused, not read as if it were", () => {
  expect(() => distance("lab(50% 40 59)", "rgb(0, 0, 0)")).toThrow(/not opaque sRGB/);
  expect(() => distance("rgb(0 0 0 / 50%)", "rgb(0, 0, 0)")).toThrow(/not opaque sRGB/);
});

test("a deficiency is simulated: red and green stay apart on a screen, and merge to a reader without green", () => {
  expect(distance("rgb(200, 0, 0)", "rgb(0, 160, 0)")).toBeGreaterThan(50);
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

test("the danger colour is the status red: one red for a failed run and a destructive action", () => {
  expect(token("danger")).toBe(token("status-failed"));
});

test("the status colours stand out from the surface and the paper, as marks", () => {
  for (const status of ["status-failed", "status-warn"]) {
    for (const ground of GROUNDS) {
      expect(
        contrast(token(status), token(ground)),
        `${status} on ${ground}`,
      ).toBeGreaterThanOrEqual(3);
    }
  }
});

test("red and gold differ in lightness, and not in hue alone", () => {
  expect(luminance(token("status-warn")) - luminance(token("status-failed"))).toBeGreaterThan(0.1);
});

test("the status colours are told apart from each other and from the chart accent, to every reader", () => {
  const colours = [token("status-failed"), token("status-warn"), token("chart-3")];
  expect(closest(colours)).toBeGreaterThanOrEqual(APART);
  for (const deficiency of DEFICIENCIES) {
    expect(closest(colours, deficiency), deficiency).toBeGreaterThanOrEqual(APART);
  }
});

test("colour-blind mode leaves the status colours as they are, whose floors the base tokens hold", () => {
  const screen = cvd();
  for (const status of ["status-failed", "status-warn", "danger"]) {
    expect(token(status, screen), status).toBe(token(status));
  }
});

test("under forced colours every pattern is on, as in colour-blind mode, whatever was chosen", async () => {
  onTestFinished(() => commands.forcedColors(false));
  const read = (name: string) => getComputedStyle(document.body).getPropertyValue(name).trim();
  expect(read("--chart-dash-2")).toBe("none");
  await commands.forcedColors(true);
  expect(read("--chart-dash-2")).toBe("6 4");
  expect(read("--chart-dash-3")).toBe("2 3");
  expect(Number(read("--chart-hatch"))).toBeGreaterThan(0);
  expect(read("--chart-marker-turn-3")).toBe("45deg");
});

test("forced colours turn on exactly the patterns colour-blind mode does: the two sets are equal", async () => {
  onTestFinished(() => commands.forcedColors(false));
  const patterns = [
    "--chart-hatch",
    "--chart-dash-2",
    "--chart-dash-3",
    "--chart-marker-size",
    "--chart-marker-display",
    "--chart-marker-corner-2",
    "--chart-marker-corner-3",
    "--chart-marker-turn-3",
  ];
  const read = (within: Element) =>
    patterns.map((name) => getComputedStyle(within).getPropertyValue(name).trim());
  const mode = read(cvd());
  expect(mode.every((value) => value !== "")).toBe(true);
  await commands.forcedColors(true);
  expect(read(document.body)).toEqual(mode);
});
