/**
 * A dashboard whose add-on won't load, as a chunk the network drops: each chart says it couldn't be
 * drawn and opens its figures, and a table is plain, never a chart drawing for ever.
 */

import { expect, onTestFinished, test, vi } from "vitest";
import { page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { DashboardView } from "./dashboard-view";
import { SUPPORT } from "./test/dashboards";

// Every add-on fails to load, as `useLoaded` says once a chunk's import is refused; that it does
// is `on-demand.test.ts`'s.
vi.mock(import("./on-demand"), () => ({
  useLoaded: () => ({ module: null, failed: true, error: new TypeError("Failed to fetch") }),
  useOnDemand: () => null,
}));

test("where the dashboards add-on won't load, a chart's figures are open, and say why", async () => {
  await page.viewport(1000, 800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(<DashboardView dashboard={SUPPORT} />);
  const bars = screen.getByRole("figure", { name: "Tickets by channel" });
  await expect
    .element(
      bars.getByText(
        "The charts couldn't be loaded here. This chart isn't drawn: its figures are below.",
      ),
    )
    .toBeVisible();
  await expect.element(bars).toHaveAttribute("aria-busy", "false");
  await expect.element(bars.getByRole("table", { name: "Tickets by channel" })).toBeVisible();
  await expect.element(screen.getByRole("table", { name: "Longest open" })).toBeVisible();
  await expect.element(screen.getByRole("searchbox")).not.toBeInTheDocument();
});
