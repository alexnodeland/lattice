import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Folded, Toolbar } from "./folded";

test("a toolbar action opens its form in a card under the row, saying what is in effect while closed", async () => {
  const screen = await render(
    <Toolbar>
      <Folded title="Find" action="Find…" said="24 hours, thread thr_1">
        <input aria-label="Thread" />
      </Folded>
    </Toolbar>,
  );
  await expect.element(screen.getByText("24 hours, thread thr_1")).toBeVisible();
  expect(screen.getByRole("region", { name: "Find" }).elements()).toHaveLength(0);
  const action = screen.getByRole("button", { name: "Find…" });
  await expect.element(action).toHaveAttribute("aria-expanded", "false");
  await action.click();
  const region = screen.getByRole("region", { name: "Find" });
  await expect.element(region.getByRole("textbox", { name: "Thread" })).toBeVisible();
  await expect.element(action).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("24 hours, thread thr_1").elements()).toHaveLength(0);
  // Under the row: the form's top is below the button's bottom.
  expect(region.element().getBoundingClientRect().top).toBeGreaterThanOrEqual(
    action.element().getBoundingClientRect().bottom,
  );
});

test("an action opens at first where the page says, and as the page holds it", async () => {
  const screen = await render(
    <Toolbar>
      <Folded title="Grant a role" action="Grant…" defaultOpen>
        <input aria-label="Role" />
      </Folded>
    </Toolbar>,
  );
  await expect.element(screen.getByRole("textbox", { name: "Role" })).toBeVisible();
  await screen.rerender(
    <Toolbar>
      <Folded title="Change ops" action="Change…" open onOpenChange={() => {}}>
        <input aria-label="Members" />
      </Folded>
    </Toolbar>,
  );
  await expect.element(screen.getByRole("textbox", { name: "Members" })).toBeVisible();
});
