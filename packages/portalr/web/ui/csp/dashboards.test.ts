/**
 * A dashboard under portalr's Content-Security-Policy, in Chromium: every panel drawn from the
 * page's own task, the dashboards add-on loaded, and then a person's hovers over the charts, a
 * table sorted and filtered, and a chart's figures opened, with not one violation of the policy
 * (portalr ADR-0047).
 */

import { type Browser, chromium } from "playwright";
import { afterAll, beforeAll, expect, test } from "vitest";
import { open } from "./harness";

let browser: Browser;

beforeAll(async () => {
  browser = await chromium.launch();
});

afterAll(() => browser.close());

test("the harness sees an eval the page itself tries, which a test's evaluate would not", async () => {
  const { page, reported } = await open(browser, "?eval");
  expect((await reported()).some((line) => line.startsWith("script-src"))).toBe(true);
  // From a test's evaluate, the same eval passes: why the dashboard draws from the page's task.
  expect(await page.evaluate(() => Function("return 1")())).toBe(1);
  await page.context().close();
});

test("a dashboard of every panel, hovered, sorted and filtered, keeps to the policy", async () => {
  const { page, reported } = await open(browser, "?dashboard");
  await page.setViewportSize({ width: 1000, height: 1600 });
  await page.locator("svg.recharts-surface").first().waitFor();
  expect(await page.getByRole("figure").count()).toBe(3);
  // A person's pointer over each chart, which opens its tooltip.
  for (const plot of await page.locator(".recharts-wrapper").all()) {
    const box = await plot.boundingBox();
    if (box) {
      for (const across of [0.2, 0.5, 0.8]) {
        await page.mouse.move(box.x + box.width * across, box.y + box.height / 2);
      }
    }
  }
  await page.getByRole("button", { name: "Days open" }).click();
  await page.getByRole("searchbox", { name: "Filter Longest open" }).fill("refund");
  await page.getByText("Rows 1 to 1 of 1.").waitFor();
  await page.getByText("Show the figures").first().click();
  expect(await reported()).toEqual([]);
  await page.context().close();
});
