import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { EmptyState } from "./empty-state";
import { contrast, token } from "./test/colours";

test("an empty state is a region named by its heading, with a sentence and one action", async () => {
  const screen = await render(
    <EmptyState title="No artifacts yet" action={<a href="#new">Start a thread</a>}>
      An artifact appears here when the agent makes one.
    </EmptyState>,
  );
  const region = screen.getByRole("region", { name: "No artifacts yet" });
  await expect.element(region.getByRole("heading", { level: 2 })).toBeVisible();
  await expect.element(region.getByRole("link", { name: "Start a thread" })).toBeVisible();
  const sentence = screen.getByText("An artifact appears here when the agent makes one.").element();
  const style = getComputedStyle(sentence);
  // A dashed box on the page, with no fill of its own (portalr ADR-0081).
  expect(getComputedStyle(region.element()).backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(getComputedStyle(region.element()).borderTopStyle).toBe("dashed");
  expect(contrast(style.color, token("paper"))).toBeGreaterThanOrEqual(4.5);
});
