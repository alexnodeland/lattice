import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Switcher, TenantSwitcher } from "./switcher";
import { contrast, token } from "./test/colours";

function Rendered({ onTenant = vi.fn(), onWorkspace = vi.fn() }) {
  return (
    <Switcher
      tenant="acme"
      workspace="notes"
      tenants={[{ id: "acme" }, { id: "globex" }]}
      workspaces={[
        { id: "notes", detail: "4 threads" },
        { id: "support", detail: "12 threads" },
      ]}
      onTenant={onTenant}
      onWorkspace={onWorkspace}
    />
  );
}

test("the switcher says where the reader is", async () => {
  const screen = await render(<Rendered />);
  await expect
    .element(screen.getByRole("button", { name: "Workspace: acme, notes" }))
    .toHaveAttribute("aria-haspopup", "menu");
});

test("on the tenant's page of workspaces, the switcher names the tenant alone and marks no workspace", async () => {
  const screen = await render(
    <Switcher
      tenant="acme"
      tenants={[{ id: "acme" }]}
      workspaces={[{ id: "notes" }, { id: "plans" }]}
      onTenant={vi.fn()}
      onWorkspace={vi.fn()}
    />,
  );
  const trigger = screen.getByRole("button", { name: "Tenant: acme" });
  await expect.element(trigger).toHaveTextContent("acme");
  await trigger.click();
  await expect
    .element(screen.getByRole("menuitemradio", { name: "notes" }))
    .toHaveAttribute("aria-checked", "false");
  await expect
    .element(screen.getByRole("menuitemradio", { name: "acme" }))
    .toHaveAttribute("aria-checked", "true");
});

test("its menu marks the current workspace and tenant, and hands over another", async () => {
  const onWorkspace = vi.fn();
  const onTenant = vi.fn();
  const screen = await render(<Rendered onWorkspace={onWorkspace} onTenant={onTenant} />);
  await screen.getByRole("button", { name: /^Workspace/ }).click();
  const menu = screen.getByRole("menu");
  await expect
    .element(menu.getByRole("menuitemradio", { name: "notes 4 threads" }))
    .toHaveAttribute("aria-checked", "true");
  await expect
    .element(menu.getByRole("menuitemradio", { name: "acme" }))
    .toHaveAttribute("aria-checked", "true");
  await menu.getByRole("menuitemradio", { name: "support 12 threads" }).click();
  expect(onWorkspace).toHaveBeenCalledExactlyOnceWith("support");
  expect(onTenant).not.toHaveBeenCalled();
});

test("the keyboard opens it, and Escape closes it, back on the switcher", async () => {
  const screen = await render(<Rendered />);
  await userEvent.tab();
  const trigger = screen.getByRole("button", { name: /^Workspace/ });
  await expect.element(trigger).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  await expect.element(screen.getByRole("menu")).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("menu")).not.toBeInTheDocument();
  await expect.element(trigger).toHaveFocus();
});

test("the item the keyboard is on is ringed and coloured, 3:1 or more from the surface", async () => {
  const screen = await render(<Rendered />);
  await userEvent.tab();
  await userEvent.keyboard("{Enter}");
  // Opened by the keyboard, the menu highlights its first item (here the current workspace, too)
  // and takes the focus: only then does the next key move the highlight. A key pressed before
  // the menu has the focus goes to the button, and is lost.
  const here = screen.getByRole("menuitemradio", { name: "notes 4 threads" });
  await expect.element(here).toHaveAttribute("data-highlighted");
  await expect
    .poll(() => screen.getByRole("menu").element().contains(document.activeElement))
    .toBe(true);
  await userEvent.keyboard("{ArrowDown}");
  const item = screen.getByRole("menuitemradio", { name: "support 12 threads" });
  await expect.element(item).toHaveAttribute("data-highlighted");
  // Read once its colours and ring have settled: a transition is never read mid-flight.
  const look = () => {
    const { color, backgroundColor, boxShadow } = getComputedStyle(item.element());
    return { color, backgroundColor, boxShadow };
  };
  let before = look();
  await expect
    .poll(() => {
      const now = look();
      const settled = JSON.stringify(now) === JSON.stringify(before);
      before = now;
      return settled && now.color === token("accent");
    })
    .toBe(true);
  const style = getComputedStyle(item.element());
  const shadows = style.boxShadow.match(/rgba?\([^)]*\)/g) ?? [];
  expect(shadows).toContain(token("focus"));
  expect(contrast(token("focus"), token("surface"))).toBeGreaterThanOrEqual(3);
  expect(style.color).toBe(token("accent"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("its menu can link to every workspace in the tenant", async () => {
  const screen = await render(
    <Switcher
      tenant="acme"
      workspace="notes"
      tenants={[{ id: "acme" }]}
      workspaces={[{ id: "notes" }]}
      onTenant={vi.fn()}
      onWorkspace={vi.fn()}
      every={<a href="#every" />}
    />,
  );
  await screen.getByRole("button", { name: /^Workspace/ }).click();
  await expect
    .element(screen.getByRole("menuitem", { name: "Every workspace in acme" }))
    .toHaveAttribute("href", "#every");
});

test("the tenant switcher names a tenant, or every tenant, and hands over another", async () => {
  const onTenant = vi.fn();
  const screen = await render(
    <TenantSwitcher
      tenant="acme"
      tenants={[{ id: "acme" }, { id: "globex" }]}
      onTenant={onTenant}
      everyTenant={<a href="#deployment" />}
    />,
  );
  await screen.getByRole("button", { name: "Tenant: acme" }).click();
  const menu = screen.getByRole("menu");
  await expect
    .element(menu.getByRole("menuitemradio", { name: "acme" }))
    .toHaveAttribute("aria-checked", "true");
  await expect
    .element(menu.getByRole("menuitem", { name: "All tenants" }))
    .toHaveAttribute("href", "#deployment");
  await menu.getByRole("menuitemradio", { name: "globex" }).click();
  expect(onTenant).toHaveBeenCalledExactlyOnceWith("globex");
});

test("every tenant is named so, and offered only to whoever may see them", async () => {
  const screen = await render(
    <TenantSwitcher tenant={null} tenants={[{ id: "acme" }]} onTenant={vi.fn()} />,
  );
  await screen.getByRole("button", { name: "Tenant: All tenants" }).click();
  await expect
    .element(screen.getByRole("menuitem", { name: "All tenants" }))
    .not.toBeInTheDocument();
});
