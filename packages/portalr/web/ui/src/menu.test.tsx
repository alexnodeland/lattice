import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { Menu } from "./menu";

test("a menu's trigger opens its actions, each chosen once, and a disabled one not at all", async () => {
  const share = vi.fn();
  const restrict = vi.fn();
  const screen = await render(
    <Menu
      label="Thread actions"
      items={[
        { label: "Share…", onSelect: share },
        { label: "Restrict", onSelect: restrict, disabled: true },
      ]}
    />,
  );
  await screen.getByRole("button", { name: "Thread actions" }).click();
  const menu = screen.getByRole("menu");
  await expect
    .element(menu.getByRole("menuitem", { name: "Restrict" }))
    .toHaveAttribute("aria-disabled", "true");
  await menu.getByRole("menuitem", { name: "Share…" }).click();
  expect(share).toHaveBeenCalledOnce();
  expect(restrict).not.toHaveBeenCalled();
});
