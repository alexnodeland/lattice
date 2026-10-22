import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Figures } from "./dashboard-figures";
import { SUPPORT } from "./test/dashboards";

/** The support dashboard's first bar chart. */
function chart() {
  for (const panel of SUPPORT.panels) {
    if (panel.type === "bar") {
      return panel;
    }
  }
  throw new Error("the support dashboard has no bar chart");
}

const PANEL = chart();

test("the figures open when the chart turns out not to be drawable, after the first render", async () => {
  const screen = await render(<Figures panel={PANEL} open={false} />);
  const trigger = screen.getByRole("button", { name: "Show the figures" });
  await expect.element(trigger).toHaveAttribute("aria-expanded", "false");
  await screen.rerender(<Figures panel={PANEL} open />);
  await expect.element(trigger).toHaveAttribute("aria-expanded", "true");
  await trigger.click();
  await expect.element(trigger).toHaveAttribute("aria-expanded", "false");
});
