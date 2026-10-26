import { expect, test } from "vitest";
import { render } from "vitest-browser-react";
import { Folded } from "./folded";

test("a folded card is a section named by its heading, closed until its line is chosen, saying what is in effect", async () => {
  const screen = await render(
    <Folded title="Find" action="Find…" said="24 hours, thread thr_1">
      <input aria-label="Thread" />
    </Folded>,
  );
  const section = screen.getByRole("region", { name: "Find" });
  await expect.element(section).toBeVisible();
  expect(section.getByRole("textbox", { name: "Thread" }).elements()).toHaveLength(0);
  const line = section.getByRole("button", { name: "Find… 24 hours, thread thr_1" });
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  await line.click();
  await expect.element(section.getByRole("textbox", { name: "Thread" })).toBeVisible();
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
});

test("a folded card opens at first where the page says, and as the page holds it", async () => {
  const screen = await render(
    <Folded title="Grant a role" action="Grant…" defaultOpen>
      <input aria-label="Role" />
    </Folded>,
  );
  await expect.element(screen.getByRole("textbox", { name: "Role" })).toBeVisible();
  await screen.rerender(
    <Folded title="Change ops" action="Change…" open onOpenChange={() => {}}>
      <input aria-label="Members" />
    </Folded>,
  );
  await expect.element(screen.getByRole("textbox", { name: "Members" })).toBeVisible();
});
