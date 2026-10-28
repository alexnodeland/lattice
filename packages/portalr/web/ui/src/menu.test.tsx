import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { glyphs } from "./icons";
import { Menu } from "./menu";

test("a menu's trigger opens its actions, each chosen once, and a disabled one not at all", async () => {
  const share = vi.fn();
  const restrict = vi.fn();
  const screen = await render(
    <Menu
      label="Thread actions"
      icon={glyphs.more}
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

test("an icon menu is an overflow: its items hold a state, shown checked, and choosing one asks for the other", async () => {
  const thumb = vi.fn();
  const screen = await render(
    <Menu
      label="Artifact actions"
      icon={glyphs.more}
      items={[
        { label: "Helpful", checked: true, onSelect: thumb },
        { label: "Not helpful", checked: false, onSelect: thumb },
      ]}
    />,
  );
  const trigger = screen.getByRole("button", { name: "Artifact actions" });
  expect(trigger.element().querySelector("svg[data-glyph]")).not.toBeNull();
  await trigger.click();
  const menu = screen.getByRole("menu");
  await expect
    .element(menu.getByRole("menuitemcheckbox", { name: "Helpful" }))
    .toHaveAttribute("aria-checked", "true");
  await expect
    .element(menu.getByRole("menuitemcheckbox", { name: "Not helpful" }))
    .toHaveAttribute("aria-checked", "false");
  await menu.getByRole("menuitemcheckbox", { name: "Not helpful" }).click();
  expect(thumb).toHaveBeenCalledOnce();
  await expect.element(screen.getByRole("menu")).not.toBeInTheDocument();
});
