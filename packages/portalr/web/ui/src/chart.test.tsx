import { expect, test } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { BarChart, DonutChart, LineChart } from "./chart";

const days = { key: "day", name: "Day" };

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
  // Each series is named at its last bar, as well as in the legend.
  await expect.poll(() => document.querySelectorAll("svg text").length).toBeGreaterThan(0);
  expect([...document.querySelectorAll("svg text")].map((text) => text.textContent)).toEqual(
    expect.arrayContaining(["Thumbs up", "Thumbs down"]),
  );
  await figure.getByText("Show the figures").click();
  const table = figure.getByRole("table", { name: "Thumbs per day" });
  await expect
    .element(table.getByRole("row", { name: "2026-10-13" }))
    .toHaveTextContent("2026-10-1324");
  // The second series is hatched, so it isn't told by its colour alone.
  expect(document.querySelectorAll("pattern").length).toBeGreaterThan(0);
});

test("a line chart draws at most three series, each its own dash, with gaps for no value", async () => {
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
  const dashes = [...document.querySelectorAll(".recharts-line-curve")].map((line) =>
    line.getAttribute("stroke-dasharray"),
  );
  expect(new Set(dashes).size).toBe(3);
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
  await expect.element(parts.first()).toHaveTextContent("notes6 · 60%");
  expect(parts.elements().map((part) => part.textContent)).toEqual([
    "notes6 · 60%",
    "plans2 · 20%",
    "ops1 · 10%",
    "Other1 · 10%",
  ]);
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
  expect(middle - top).toBeGreaterThanOrEqual(12);
  expect(bottom - middle).toBeGreaterThanOrEqual(12);
});

test("labels stay inside the plot, and a long name is cut, and given whole as a title", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <LineChart
      label="All at the floor"
      index={days}
      series={[
        { key: "a", name: "an evaluation with a long name" },
        { key: "b", name: "b" },
        { key: "c", name: "c" },
      ]}
      data={[{ day: "2026-10-12", a: 0, b: 0, c: 0 }]}
      domain={[0, 1]}
    />,
  );
  await expect.element(screen.getByRole("figure", { name: "All at the floor" })).toBeVisible();
  await expect.poll(() => document.querySelectorAll("svg text title").length).toBe(1);
  expect(document.querySelector("svg text title")?.textContent).toBe(
    "an evaluation with a long name",
  );
  const labels = [...document.querySelectorAll("svg text")].filter((text) =>
    ["an evaluation…", "b", "c"].includes(text.lastChild?.textContent ?? ""),
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
