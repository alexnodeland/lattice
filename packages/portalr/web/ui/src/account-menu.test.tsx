import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AccountMenu } from "./account-menu";
import { viewport } from "./test/viewport";

test("the account menu is named for who is signed in", async () => {
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      colourBlind={false}
      onColourBlind={vi.fn()}
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
      colourBlind={false}
      onColourBlind={vi.fn()}
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
  await viewport(390);
  const props = {
    name: "alice@portalr.test",
    appearance: "system" as const,
    colourBlind: false,
    onColourBlind: vi.fn(),
  };
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
  const [bar, drawer] = screen.getByRole("button", { name: /^Account: / }).elements();
  // What a button shows, as a person reads it: a hidden name isn't in it.
  expect((bar as HTMLElement).innerText).not.toContain("alice@portalr.test");
  expect((drawer as HTMLElement).innerText).toContain("alice@portalr.test");
});

test("colour-blind friendly charts are a switch in the menu: a checkbox item that says whether it is on", async () => {
  const onColourBlind = vi.fn();
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={onColourBlind}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", { name: "Colour-blind friendly charts" });
  await expect.element(item).toHaveAttribute("aria-checked", "false");
  await item.click();
  expect(onColourBlind).toHaveBeenCalledExactlyOnceWith(true);
});

test("when it is on, the item says so, and a click turns it off", async () => {
  const onColourBlind = vi.fn();
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="dark"
      onAppearance={vi.fn()}
      colourBlind
      onColourBlind={onColourBlind}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", { name: "Colour-blind friendly charts" });
  await expect.element(item).toHaveAttribute("aria-checked", "true");
  await item.click();
  expect(onColourBlind).toHaveBeenCalledExactlyOnceWith(false);
});

test("the keyboard reaches it and a key toggles it", async () => {
  const onColourBlind = vi.fn();
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={onColourBlind}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", { name: "Colour-blind friendly charts" });
  await expect.element(item).toBeVisible();
  await item.element().focus();
  await expect.element(item).toHaveFocus();
  await userEvent.keyboard(" ");
  expect(onColourBlind).toHaveBeenCalledExactlyOnceWith(true);
});

test("the switch says what it does, as its description, and its name is the words alone", async () => {
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={vi.fn()}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", { name: "Colour-blind friendly charts" });
  await expect.element(item).toHaveAccessibleName("Colour-blind friendly charts");
  await expect.element(item).toHaveAccessibleDescription("Changes chart colours and adds patterns");
});

test("without product analytics there is no switch for it", async () => {
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={vi.fn()}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Colour-blind friendly charts" }))
    .toBeVisible();
  expect(
    screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }).elements(),
  ).toHaveLength(0);
});

test("sharing how the app is used is off until the person turns it on, and says what it shares", async () => {
  const onAnswer = vi.fn();
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={vi.fn()}
      analytics={{ given: false, onAnswer }}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" });
  await expect.element(item).toHaveAttribute("aria-checked", "false");
  await expect
    .element(item)
    .toHaveAccessibleDescription(
      "Which pages and features you open, never what you write. Off deletes it.",
    );
  await item.click();
  expect(onAnswer).toHaveBeenCalledExactlyOnceWith(true);
});

test("turned on, a click turns sharing off, as easily as it was turned on", async () => {
  const onAnswer = vi.fn();
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={vi.fn()}
      analytics={{ given: true, onAnswer }}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" });
  await expect.element(item).toHaveAttribute("aria-checked", "true");
  await item.click();
  expect(onAnswer).toHaveBeenCalledExactlyOnceWith(false);
});
