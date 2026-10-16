import { expect, onTestFinished, test } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { BarChart, DonutChart, LineChart } from "./chart";
import { formatDay } from "./chart-theme";

const days = { key: "day", name: "Day" };

/** What the chart's text says, in the drawing. */
/** A series name long enough that no chart gives it room whole. */
const LONG = "an evaluation of the answers with a very long name that no chart has room for";

const texts = () => [...document.querySelectorAll("svg text")].map((text) => text.textContent);

/** The page asks for colour-blind mode, as it would on its root. */
function colourBlind() {
  document.documentElement.dataset.cvd = "";
  onTestFinished(() => {
    delete document.documentElement.dataset.cvd;
  });
}

test("a diverging bar chart names its series, labels them, and gives its figures as counts", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <BarChart
      label="Thumbs per day"
      index={days}
      series={[
        { key: "up", name: "Thumbs up" },
        { key: "down", name: "Thumbs down" },
      ]}
      data={[
        { day: "2026-10-12", up: 3, down: 1 },
        { day: "2026-10-13", up: 2, down: 4 },
      ]}
      diverging
    />,
  );
  const figure = screen.getByRole("figure", { name: "Thumbs per day" });
  await expect.element(figure).toBeVisible();
  await expect.element(figure.getByRole("listitem").first()).toHaveTextContent("Thumbs up");
  // Each half is named at the axis, as well as in the legend.
  await expect.poll(texts).toEqual(expect.arrayContaining(["Thumbs up", "Thumbs down"]));
  // Both halves count up from the baseline, in whole numbers, so the lower one reads as counts.
  await expect
    .poll(() => document.querySelectorAll(".recharts-yAxis-tick-labels text").length)
    .toBe(5);
  const ticks = [...document.querySelectorAll(".recharts-yAxis-tick-labels text")];
  expect(ticks.map((tick) => tick.textContent)).toEqual(["4", "2", "0", "2", "4"]);
  await figure.getByText("Show the figures").click();
  const table = figure.getByRole("table", { name: "Thumbs per day" });
  await expect
    .element(table.getByRole("row", { name: "2026-10-13" }))
    .toHaveTextContent("2026-10-1324");
});

test("a diverging chart's halves meet at the baseline, so the second is hatched; a lone series is solid", async () => {
  await page.viewport(1024, 768);
  await render(
    <BarChart
      label="Thumbs"
      index={days}
      series={[
        { key: "up", name: "Thumbs up" },
        { key: "down", name: "Thumbs down" },
      ]}
      data={[{ day: "2026-10-12", up: 3, down: 1 }]}
      diverging
    />,
  );
  await expect.poll(() => document.querySelectorAll("pattern").length).toBeGreaterThan(0);
  const stripe = document.querySelector("pattern line");
  expect(Number(getComputedStyle(stripe as Element).strokeOpacity)).toBeGreaterThan(0);
});

test("a chart that nothing touches draws solid fills, with no hatch to see", async () => {
  await page.viewport(1024, 768);
  await render(
    <BarChart
      label="Spend"
      index={days}
      series={[
        { key: "a", name: "A" },
        { key: "b", name: "B" },
      ]}
      data={[{ day: "2026-10-12", a: 3, b: 1 }]}
    />,
  );
  await expect.poll(() => document.querySelectorAll("pattern").length).toBeGreaterThan(0);
  const stripe = document.querySelector("pattern line");
  expect(Number(getComputedStyle(stripe as Element).strokeOpacity)).toBe(0);
  // Colour-blind mode hatches it, wherever it is drawn.
  colourBlind();
  await expect
    .poll(() =>
      Number(getComputedStyle(document.querySelector("pattern line") as Element).strokeOpacity),
    )
    .toBeGreaterThan(0);
});

test("a series on its own is named by the legend and the caption, not by a label at its end", async () => {
  await page.viewport(1024, 768);
  await render(
    <BarChart
      label="Spend per day"
      index={days}
      series={[{ key: "spend", name: "Spend" }]}
      data={[{ day: "2026-10-12", spend: 3 }]}
    />,
  );
  await expect.poll(() => document.querySelectorAll(".recharts-bar-rectangle").length).toBe(1);
  expect(texts()).not.toContain("Spend");
});

test("a value axis is on one line, as wide as its widest tick, with its unit", async () => {
  await page.viewport(390, 844);
  await render(
    <LineChart
      label="Latency"
      index={days}
      series={[{ key: "p95", name: "95th percentile" }]}
      data={[
        { day: "2026-10-12", p95: 0.24 },
        { day: "2026-10-13", p95: 0.12 },
      ]}
      format={(value) => `${value.toFixed(2)} s`}
    />,
  );
  await expect
    .poll(() => document.querySelectorAll(".recharts-yAxis-tick-labels text").length)
    .toBeGreaterThan(1);
  await expect
    .poll(() => document.querySelectorAll(".recharts-yAxis-tick-labels text").length)
    .toBe(5);
  const ticks = [...document.querySelectorAll(".recharts-yAxis-tick-labels text")];
  for (const tick of ticks) {
    expect(tick.querySelectorAll("tspan"), tick.textContent ?? "").toHaveLength(1);
    expect(tick.textContent).toMatch(/^\d\.\d\d s$/);
  }
  // Each is whole in the drawing, none clipped by its left edge.
  const edge = document.querySelector(".recharts-surface")?.getBoundingClientRect().left ?? 0;
  for (const tick of ticks) {
    expect(tick.getBoundingClientRect().left).toBeGreaterThanOrEqual(edge);
  }
});

test("a tooltip is on the menus' surface, with each series' mark, name and aligned value", async () => {
  await page.viewport(1024, 768);
  await render(
    <BarChart
      label="Spend"
      index={days}
      series={[{ key: "spend", name: "Spend" }]}
      data={[
        { day: "2026-10-12", spend: 12.5 },
        { day: "2026-10-13", spend: 30 },
      ]}
      format={(value) => `$${value.toFixed(2)}`}
      tick={formatDay}
    />,
  );
  await expect.poll(() => document.querySelectorAll(".recharts-bar-rectangle").length).toBe(2);
  await userEvent.hover(
    page.elementLocator(document.querySelectorAll(".recharts-bar-rectangle")[1] as Element),
  );
  await expect
    .poll(() => document.querySelector(".recharts-tooltip-wrapper .shadow-lg"))
    .not.toBeNull();
  const card = document.querySelector(".recharts-tooltip-wrapper .shadow-lg") as HTMLElement;
  expect(card.textContent).toBe("2026-10-13Spend$30.00");
  // The menus' surface: a border, a raised shadow and the surface's colour.
  expect(getComputedStyle(card).borderTopWidth).toBe("1px");
  expect(card.querySelector("svg")).not.toBeNull();
  // Its digits are aligned and its point is not: the figures' digits are tabular, "." is not.
  const digits = [...card.querySelectorAll(".tabular-nums")].map((span) => span.textContent);
  expect(digits).toEqual(["30", "00"]);
});

test("a line chart draws at most three series, unbroken, and dashes each in colour-blind mode", async () => {
  await page.viewport(1024, 768);
  const series = ["a", "b", "c", "d"].map((key) => ({ key, name: `Series ${key}` }));
  const screen = await render(
    <LineChart
      label="Mean score per day"
      index={days}
      series={series}
      data={[
        { day: "2026-10-12", a: 0.5, b: null, c: 1, d: 0 },
        { day: "2026-10-13", a: 0.75, b: 0.25, c: 1, d: 0 },
      ]}
      domain={[0, 1]}
      format={(value) => value.toFixed(2)}
    />,
  );
  const figure = screen.getByRole("figure", { name: "Mean score per day" });
  await expect.element(figure.getByRole("listitem")).toHaveLength(3);
  await expect.element(figure.getByText("Series d")).not.toBeInTheDocument();
  await expect.poll(() => document.querySelectorAll(".recharts-line-curve").length).toBe(3);
  const dashes = () =>
    [...document.querySelectorAll(".recharts-line-curve")].map(
      (line) => getComputedStyle(line).strokeDasharray,
    );
  expect(new Set(dashes())).toEqual(new Set(["none"]));
  colourBlind();
  await expect.poll(() => new Set(dashes()).size).toBe(3);
  // The markers differ too: a circle, then a square, then a diamond.
  const shapes = [...document.querySelectorAll(".recharts-line-dots")].map((line) => {
    const marker = getComputedStyle(line.querySelector("rect") as Element);
    return `${marker.rx} ${marker.transform}`;
  });
  expect(new Set(shapes).size).toBe(3);
  await figure.getByText("Show the figures").click();
  await expect
    .element(figure.getByRole("row", { name: "2026-10-12" }))
    .toHaveTextContent("2026-10-120.50–1.00");
});

test("a donut shows the largest three parts, folds the rest into Other, and gives each share", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <DonutChart
      label="Feedback by workspace"
      parts={[
        { key: "notes", name: "notes", value: 6 },
        { key: "plans", name: "plans", value: 2 },
        { key: "ops", name: "ops", value: 1 },
        { key: "infra", name: "infra", value: 1 },
        // A part named as "Other" is would be, kept apart from it by its key.
        { key: "other", name: "Other", value: 0 },
      ]}
    />,
  );
  const figure = screen.getByRole("figure", { name: "Feedback by workspace" });
  const parts = figure.getByRole("listitem");
  await expect.element(parts.first()).toHaveTextContent("notes660%");
  // Each part's name, value and share, in its own row.
  expect(
    parts.elements().map((part) => [...part.children].map((cell) => cell.textContent)),
  ).toEqual([
    ["notes", "6", "60%"],
    ["plans", "2", "20%"],
    ["ops", "1", "10%"],
    ["Other", "1", "10%"],
  ]);
  // The whole is at the centre of the ring.
  await expect.element(figure.getByText("Total")).toBeVisible();
  expect(figure.getByText("Total").element().parentElement?.textContent).toBe("Total10");
  await figure.getByText("Show the figures").click();
  await expect.element(figure.getByRole("row", { name: "infra" })).toHaveTextContent("infra110%");
  await expect.element(figure.getByRole("row", { name: "Other" })).not.toBeInTheDocument();
});

test("a line keeps its sign, a line ending at 0 is named, and labels don't overlap", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <LineChart
      label="Means"
      index={{ key: "day", name: "Day (UTC)" }}
      series={[
        { key: "a", name: "falls" },
        { key: "b", name: "zero" },
        { key: "c", name: "near" },
      ]}
      data={[
        { day: "10-12", a: 0.25, b: 0.5, c: 0.01 },
        { day: "10-13", a: -0.5, b: 0, c: 0.02 },
      ]}
      format={(value) => value.toFixed(2)}
    />,
  );
  const figure = screen.getByRole("figure", { name: "Means" });
  await figure.getByText("Show the figures").click();
  await expect
    .element(figure.getByRole("row", { name: "10-13" }))
    .toHaveTextContent("10-13-0.500.000.02");
  await expect.poll(() => document.querySelectorAll("svg text").length).toBeGreaterThan(0);
  const labels = [...document.querySelectorAll("svg text")].filter((text) =>
    ["falls", "zero", "near"].includes(text.textContent ?? ""),
  );
  expect(labels.map((text) => text.textContent).sort()).toEqual(["falls", "near", "zero"]);
  const [top = 0, middle = 0, bottom = 0] = labels
    .map((text) => Number(text.getAttribute("y")))
    .sort((a, b) => a - b);
  // A line of the chart's text, within a hair of rounding.
  expect(middle - top).toBeGreaterThanOrEqual(11.99);
  expect(bottom - middle).toBeGreaterThanOrEqual(11.99);
});

test("labels stay inside the plot, a name that fits is whole, and one too long is cut, and given whole as a title", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <LineChart
      label="All at the floor"
      index={days}
      series={[
        { key: "a", name: LONG },
        { key: "b", name: "accuracy · accuracy" },
        { key: "c", name: "c" },
      ]}
      data={[{ day: "2026-10-12", a: 0, b: 0, c: 0 }]}
      domain={[0, 1]}
    />,
  );
  await expect.element(screen.getByRole("figure", { name: "All at the floor" })).toBeVisible();
  await expect.poll(() => document.querySelectorAll("svg text title").length).toBe(1);
  expect(document.querySelector("svg text title")?.textContent).toBe(LONG);
  const written = [...document.querySelectorAll("svg text")].map(
    (text) => text.lastChild?.textContent,
  );
  // A name of 19 characters has room to spare at this width, so it is whole; the long one is cut.
  expect(written).toContain("accuracy · accuracy");
  expect(written.some((text) => text?.endsWith("…") && LONG.startsWith(text.slice(0, 8)))).toBe(
    true,
  );
  const labels = [...document.querySelectorAll("svg text")].filter(
    (text) =>
      ["accuracy · accuracy", "c"].includes(text.lastChild?.textContent ?? "") ||
      text.lastChild?.textContent?.endsWith("…"),
  );
  expect(labels).toHaveLength(3);
  const floor = Math.max(
    ...[...document.querySelectorAll(".recharts-cartesian-grid-horizontal line")].map((line) =>
      Number(line.getAttribute("y1")),
    ),
  );
  // Each label's middle, 4px above its baseline, is inside the plot.
  for (const label of labels) {
    expect(Number(label.getAttribute("y")) - 4).toBeLessThanOrEqual(floor);
  }
});

test("the first rows a read didn't reach are shaded, and named so", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <BarChart
      label="Partly read"
      index={days}
      series={[{ key: "up", name: "Thumbs up" }]}
      data={[
        { day: "10-11", up: null },
        { day: "10-12", up: null },
        { day: "10-13", up: 2 },
      ]}
      unknown={2}
    />,
  );
  await expect.element(screen.getByRole("figure", { name: "Partly read" })).toBeVisible();
  await expect.poll(() => document.querySelectorAll(".recharts-reference-area").length).toBe(1);
  expect([...document.querySelectorAll("svg text")].map((text) => text.textContent)).toContain(
    "Not read",
  );
});

test("an axis may write an index shorter than the table does", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <BarChart
      label="Spend"
      index={days}
      series={[{ key: "up", name: "Spend" }]}
      data={[
        { day: "2025-12-31", up: 1 },
        { day: "2026-01-01", up: 2 },
      ]}
      tick={formatDay}
    />,
  );
  const figure = screen.getByRole("figure", { name: "Spend" });
  await expect.poll(texts).toEqual(expect.arrayContaining(["Dec 31", "Jan 1"]));
  await figure.getByText("Show the figures").click();
  await expect.element(figure.getByRole("row", { name: "2025-12-31" })).toBeVisible();
});

test("on a phone, each direct label is whole and inside the drawing", async () => {
  await page.viewport(390, 844);
  await render(
    <div style={{ width: 346 }}>
      <LineChart
        label="Means"
        index={days}
        series={[
          { key: "a", name: "Thumbs down" },
          { key: "b", name: "95th percentile" },
          { key: "c", name: "Spend" },
        ]}
        data={[
          { day: "2026-10-12", a: 0.2, b: 0.5, c: 0.9 },
          { day: "2026-10-13", a: 0.3, b: 0.6, c: 0.8 },
        ]}
        domain={[0, 1]}
      />
    </div>,
  );
  await expect.poll(() => texts().includes("Thumbs down")).toBe(true);
  const svg = document.querySelector(".recharts-surface")?.getBoundingClientRect();
  const labels = [...document.querySelectorAll("svg text")].filter((text) =>
    ["Thumbs down", "95th percentile", "Spend"].includes(text.lastChild?.textContent ?? ""),
  );
  expect(labels).toHaveLength(3);
  for (const label of labels) {
    expect(label.getBoundingClientRect().right).toBeLessThanOrEqual((svg?.right ?? 0) + 0.5);
  }
});

test("on a phone, a donut's legend keeps each part's value in its row, with its name", async () => {
  await page.viewport(390, 844);
  const screen = await render(
    <div style={{ width: 346 }}>
      <DonutChart
        label="Spend by workspace"
        parts={[
          { key: "a", name: "a long workspace name", value: 38.19 },
          { key: "b", name: "notes", value: 6.4 },
        ]}
        format={(value) => `$${value.toFixed(2)}`}
      />
    </div>,
  );
  const rows = screen.getByRole("figure").getByRole("listitem").elements();
  expect(rows).toHaveLength(2);
  for (const row of rows) {
    const [name, value] = [...row.children].map((cell) => cell.getBoundingClientRect());
    // The value sits on the name's line, not under it, and close to it.
    expect(Math.abs((value?.top ?? 0) - (name?.top ?? 0))).toBeLessThan(8);
    expect((value?.left ?? 0) - (name?.right ?? 0)).toBeLessThan(48);
  }
});

test("labels of the widest letters still fit the drawing, as measured, not as guessed", async () => {
  await page.viewport(390, 844);
  const name = "WWWWWWWWWWWWWW";
  await render(
    <div style={{ width: 346 }}>
      <LineChart
        label="Wide"
        index={days}
        series={[
          { key: "a", name },
          { key: "b", name: `${name}M` },
        ]}
        data={[{ day: "2026-10-12", a: 0.2, b: 0.8 }]}
        domain={[0, 1]}
      />
    </div>,
  );
  await expect.poll(() => texts().filter((text) => text?.startsWith("WWWW")).length).toBe(2);
  const svg = document.querySelector(".recharts-surface")?.getBoundingClientRect();
  for (const label of [...document.querySelectorAll("svg text")].filter((text) =>
    text.textContent?.startsWith("WWWW"),
  )) {
    expect(label.getBoundingClientRect().right).toBeLessThanOrEqual((svg?.right ?? 0) + 0.5);
  }
});
