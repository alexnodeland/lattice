/**
 * The charts' look, pinned by screenshots (portalr ADR-0019, ADR-0036): each chart with fixed
 * figures, wide and narrow, in each scheme, and again in colour-blind mode. Like the gallery's,
 * the baselines are Linux's, made in CI, with motion reduced and the self-hosted faces loaded.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { BarChart, DonutChart, LineChart } from "./chart";
import { formatDay } from "./chart-theme";
import { dark } from "./test/colours";
import { Tracker } from "./tracker";

const DAYS = Array.from({ length: 14 }, (_, at) => `2026-10-${String(at + 1).padStart(2, "0")}`);
const THUMBS = [
  [3, 1],
  [5, 0],
  [4, 2],
  [6, 1],
  [2, 3],
  [0, 0],
  [1, 1],
  [4, 0],
  [7, 2],
  [5, 1],
  [3, 4],
  [2, 0],
  [6, 1],
  [4, 2],
] as const;
const SPEND = [1.2, 2.8, 3.1, 4.6, 2.2, 0, 0.8, 3.3, 5.2, 4.1, 2.9, 1.5, 3.8, 4.9];
const MEANS = [0.62, 0.7, 0.74, 0.69, 0.78, null, 0.81, 0.77, 0.83, 0.88, 0.86, 0.9, 0.87, 0.92];

const day = { key: "day", name: "Day (UTC)" };
const dollars = (value: number) => `$${value.toFixed(2)}`;

function Charts() {
  return (
    <div data-testid="charts" className="flex flex-col gap-8 bg-paper p-4 text-fg">
      <BarChart
        label="People's thumbs per day"
        index={day}
        series={[
          { key: "up", name: "Thumbs up" },
          { key: "down", name: "Thumbs down" },
        ]}
        data={DAYS.map((one, at) => ({
          day: one,
          up: THUMBS[at]?.[0] ?? 0,
          down: THUMBS[at]?.[1] ?? 0,
        }))}
        tick={formatDay}
        whole
        diverging
      />
      <LineChart
        label="Each evaluation's mean per day"
        index={day}
        series={[
          { key: "accuracy", name: "accuracy" },
          { key: "safe", name: "safe" },
          { key: "polite", name: "polite" },
        ]}
        data={DAYS.map((one, at) => ({
          day: one,
          accuracy: MEANS[at] ?? null,
          safe: Math.min(1, (MEANS[at] ?? 0.7) + 0.12),
          polite: Math.max(0, (MEANS[at] ?? 0.7) - 0.2),
        }))}
        domain={[0, 1]}
        format={(value) => value.toFixed(2)}
        tick={formatDay}
      />
      <BarChart
        label="Spend per day"
        index={day}
        series={[{ key: "spend", name: "Spend" }]}
        data={DAYS.map((one, at) => ({ day: one, spend: SPEND[at] ?? 0 }))}
        format={dollars}
        tick={formatDay}
      />
      <DonutChart
        label="Spend by workspace"
        parts={[
          { key: "notes", name: "notes", value: 34.2 },
          { key: "plans", name: "plans", value: 18.9 },
          { key: "ops", name: "ops", value: 6.4 },
          { key: "infra", name: "infra", value: 2.5 },
        ]}
        format={dollars}
      />
      <Tracker
        label="Each day's spend against its share of the budget"
        index="Day (UTC)"
        figure="Spend"
        levels={[
          { key: "none", name: "Nothing spent" },
          { key: "under", name: "Under its share" },
          { key: "near", name: "Near its share (80% or more)" },
          { key: "over", name: "Over its share" },
        ]}
        blocks={DAYS.map((one, at) => ({
          key: one,
          name: one,
          level: [0, 1, 1, 3, 1, 0, 1, 2, 3, 3, 2, 1, 2, 3][at] ?? 0,
          figure: dollars(SPEND[at] ?? 0),
        }))}
      />
    </div>
  );
}

/** The charts laid out at a width, with the faces loaded and the drawings settled. */
async function shown(width: number, colourBlind = false) {
  await page.viewport(width, 2400);
  onTestFinished(() => page.viewport(414, 896));
  if (colourBlind) {
    document.documentElement.dataset.cvd = "";
    onTestFinished(() => {
      delete document.documentElement.dataset.cvd;
    });
  }
  await render(<Charts />);
  // The pointer rests off the charts, so no tooltip is open in the shot.
  await commands.pointerAway();
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  // The drawings measure their labels once the faces are in, and draw again: wait for both.
  await document.fonts.ready;
  await new Promise((settled) => requestAnimationFrame(() => requestAnimationFrame(settled)));
  await expect.poll(() => document.querySelectorAll("svg text").length).toBeGreaterThan(20);
}

async function matches(name: string) {
  await expect(page.getByTestId("charts")).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("the charts, wide", async () => {
  await shown(900);
  await matches("charts-wide");
});

test("the charts, narrow", async () => {
  await shown(390);
  await matches("charts-narrow");
});

test("the charts, in colour-blind mode", async () => {
  await shown(900, true);
  await matches("charts-colour-blind");
});
