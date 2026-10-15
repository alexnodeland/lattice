import { expect, onTestFinished, test, vi } from "vitest";
import { page } from "vitest/browser";
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
  const signedIn = menu.getByRole("group", { name: "Alex Nodeland alex@acme.test" });
  await expect.element(signedIn.getByRole("menuitem", { name: "Sign out" })).toBeVisible();
  await expect
    .element(menu.getByRole("menuitemradio", { name: "Follow the system" }))
    .toHaveAttribute("aria-checked", "true");
  await menu.getByRole("menuitemradio", { name: "Dark" }).click();
  expect(onAppearance).toHaveBeenCalledExactlyOnceWith("dark");
  await menu.getByRole("menuitem", { name: "Sign out" }).click();
  expect(onSignOut).toHaveBeenCalledOnce();
});

test("below the rail's width the name is hidden, but not in the drawer", async () => {
  await page.viewport(390, 800);
  onTestFinished(() => page.viewport(414, 896));
  const props = { name: "alice@portalr.test", appearance: "system" as const };
  const screen = await render(
    <>
      <div id="bar">
        <AccountMenu {...props} onAppearance={vi.fn()} onSignOut={vi.fn()} />
      </div>
      <div data-drawer="">
        <AccountMenu {...props} onAppearance={vi.fn()} onSignOut={vi.fn()} />
      </div>
    </>,
  );
  await expect.element(screen.getByText("alice@portalr.test").last()).toBeVisible();
  const names = [...document.querySelectorAll("button span.truncate")];
  expect(names.map((name) => getComputedStyle(name).display)).toEqual(["none", "block"]);
});
