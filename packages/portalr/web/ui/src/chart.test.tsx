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
  await expect.element(table.getByRole("row", { name: "2026-10-13 2 4" })).toBeVisible();
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
  await expect.element(figure.getByRole("row", { name: "2026-10-12 0.50 – 1.00" })).toBeVisible();
});

test("a donut shows the largest three parts, folds the rest into Other, and gives each share", async () => {
  await page.viewport(1024, 768);
  const screen = await render(
    <DonutChart
      label="Feedback by workspace"
      parts={[
        { name: "notes", value: 6 },
        { name: "plans", value: 2 },
        { name: "ops", value: 1 },
        { name: "infra", value: 1 },
        { name: "empty", value: 0 },
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
  await expect.element(figure.getByRole("row", { name: "infra 1 10%" })).toBeVisible();
  await expect.element(figure.getByRole("row", { name: /^empty/ })).not.toBeInTheDocument();
});
