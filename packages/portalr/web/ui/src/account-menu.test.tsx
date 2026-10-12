import { expect, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { AccountMenu } from "./account-menu";

test("the account menu is named for who is signed in", async () => {
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      onSignOut={vi.fn()}
    />,
  );
  await expect
    .element(screen.getByRole("button", { name: "Account: Alex Nodeland" }))
    .toHaveTextContent("ANAlex Nodeland");
});

test("it holds the scheme, chosen among three, and signing out", async () => {
  const onAppearance = vi.fn();
  const onSignOut = vi.fn();
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      email="alex@acme.test"
      appearance="system"
      onAppearance={onAppearance}
      onSignOut={onSignOut}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const menu = screen.getByRole("menu");
  await expect.element(menu.getByText("alex@acme.test")).toBeVisible();
  await expect
    .element(menu.getByRole("menuitemradio", { name: "Follow the system" }))
    .toHaveAttribute("aria-checked", "true");
  await menu.getByRole("menuitemradio", { name: "Dark" }).click();
  expect(onAppearance).toHaveBeenCalledExactlyOnceWith("dark");
  await menu.getByRole("menuitem", { name: "Sign out" }).click();
  expect(onSignOut).toHaveBeenCalledOnce();
});
