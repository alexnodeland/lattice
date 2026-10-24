import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AccountMenu, analyticsStatus } from "./account-menu";
import { axeViolations } from "./test/axe";
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

const GUIDE = "https://lattice.example/portalr/guides/privacy/";

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
      analytics={{ given: false, onAnswer, guide: GUIDE }}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" });
  await expect.element(item).toHaveAttribute("aria-checked", "false");
  await expect
    .element(item)
    .toHaveAccessibleDescription(
      "Which pages you open, never what you write. Turning it off deletes what you shared.",
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
      analytics={{ given: true, onAnswer, guide: GUIDE }}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" });
  await expect.element(item).toHaveAttribute("aria-checked", "true");
  await item.click();
  expect(onAnswer).toHaveBeenCalledExactlyOnceWith(false);
});

test("the switch is beside a link to what is shared, and says when a deletion is still to be done", async () => {
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={vi.fn()}
      analytics={{ given: false, onAnswer: vi.fn(), deleting: true, guide: GUIDE }}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const link = screen.getByRole("menuitem", {
    name: "What is shared, and how it is kept (opens in a new tab)",
  });
  await expect.element(link).toHaveAttribute("href", GUIDE);
  await expect
    .element(
      screen.getByText(
        "Deleting what you shared hasn't finished yet. It will be retried until it is done.",
      ),
    )
    .toBeVisible();
});

test("what a screen reader hears as the answer changes", () => {
  const guide = GUIDE;
  const onAnswer = vi.fn();
  expect(analyticsStatus(undefined)).toBe("");
  expect(analyticsStatus({ given: true, onAnswer, guide })).toBe(
    "Sharing how you use the app is on.",
  );
  expect(analyticsStatus({ given: false, onAnswer, guide })).toBe(
    "Sharing how you use the app is off.",
  );
  expect(analyticsStatus({ given: true, onAnswer, guide, failed: true })).toBe(
    "Your answer wasn't saved, so nothing has changed. Try again. Sharing how you use the app is on.",
  );
  expect(analyticsStatus({ given: false, onAnswer, guide, deleting: true })).toBe(
    "Sharing is off. Deleting what you shared hasn't finished yet. It will be retried until it is done.",
  );
});

const WORDS = {
  label: "Record my sessions to improve the app",
  about:
    "Records the layout of the pages you visit and where you click. All text and anything you type is hidden, and chats, files, mini apps and Access are never recorded. Turning it off deletes your recordings.",
  link: "What is recorded, and how it is kept (opens in a new tab)",
  pending: "Deleting your recordings hasn't finished yet. It will be retried until it is done.",
};
const REPLAY_GUIDE = `${GUIDE}#session-replay`;

function withReplay(
  analytics: { given: boolean },
  replay: { given: boolean; deleting?: boolean },
  onAnswer = vi.fn(),
) {
  return (
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={vi.fn()}
      analytics={{
        given: analytics.given,
        onAnswer: vi.fn(),
        guide: GUIDE,
        replay: { ...replay, onAnswer, guide: REPLAY_GUIDE, words: WORDS },
      }}
      onSignOut={vi.fn()}
    />
  );
}

test("without session replay in the deployment there is no switch for it", async () => {
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={vi.fn()}
      analytics={{ given: true, onAnswer: vi.fn(), guide: GUIDE }}
      onSignOut={vi.fn()}
    />,
  );
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Share how I use the app" }))
    .toBeVisible();
  expect(
    screen
      .getByRole("menuitemcheckbox", { name: "Record my sessions to improve the app" })
      .elements(),
  ).toHaveLength(0);
});

test("recording sessions is off until the person turns it on, and says what it records and hides", async () => {
  const onAnswer = vi.fn();
  const screen = await render(withReplay({ given: true }, { given: false }, onAnswer));
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", {
    name: "Record my sessions to improve the app",
  });
  await expect.element(item).toHaveAttribute("aria-checked", "false");
  await expect.element(item).toHaveAccessibleName("Record my sessions to improve the app");
  await expect.element(item).toHaveAccessibleDescription(WORDS.about);
  await item.click();
  expect(onAnswer).toHaveBeenCalledExactlyOnceWith(true);
});

test("turned on, a click turns recording off, as easily as it was turned on", async () => {
  const onAnswer = vi.fn();
  const screen = await render(withReplay({ given: true }, { given: true }, onAnswer));
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", {
    name: "Record my sessions to improve the app",
  });
  await expect.element(item).toHaveAttribute("aria-checked", "true");
  await item.click();
  expect(onAnswer).toHaveBeenCalledExactlyOnceWith(false);
});

test("the keyboard reaches the recording switch and a key toggles it", async () => {
  const onAnswer = vi.fn();
  const screen = await render(withReplay({ given: true }, { given: false }, onAnswer));
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const item = screen.getByRole("menuitemcheckbox", {
    name: "Record my sessions to improve the app",
  });
  await expect.element(item).toBeVisible();
  await item.element().focus();
  await expect.element(item).toHaveFocus();
  await userEvent.keyboard(" ");
  expect(onAnswer).toHaveBeenCalledExactlyOnceWith(true);
});

test("the recording switch is beside a link to what is recorded, which opens in a new tab", async () => {
  const screen = await render(withReplay({ given: true }, { given: false }));
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  const link = screen.getByRole("menuitem", {
    name: "What is recorded, and how it is kept (opens in a new tab)",
  });
  await expect.element(link).toHaveAttribute("href", REPLAY_GUIDE);
  await expect.element(link).toHaveAttribute("target", "_blank");
  await expect.element(link).toHaveAttribute("rel", "noopener noreferrer");
});

test("a deletion of recordings still to be done is said beside the switch", async () => {
  const screen = await render(withReplay({ given: true }, { given: false, deleting: true }));
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  await expect.element(screen.getByText(WORDS.pending)).toBeVisible();
  await expect
    .element(
      screen.getByRole("menuitemcheckbox", { name: "Record my sessions to improve the app" }),
    )
    .toBeVisible();
});

test("without the person's yes to sharing there is nothing to turn on, but a deletion owed is still said", async () => {
  const quiet = await render(withReplay({ given: false }, { given: false }));
  await quiet.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  await expect
    .element(quiet.getByRole("menuitemcheckbox", { name: "Share how I use the app" }))
    .toBeVisible();
  expect(
    quiet
      .getByRole("menuitemcheckbox", { name: "Record my sessions to improve the app" })
      .elements(),
  ).toHaveLength(0);
  expect(quiet.getByText(WORDS.pending).elements()).toHaveLength(0);
  await quiet.unmount();

  const owing = await render(withReplay({ given: false }, { given: false, deleting: true }));
  await owing.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  await expect.element(owing.getByText(WORDS.pending)).toBeVisible();
  expect(
    owing
      .getByRole("menuitemcheckbox", { name: "Record my sessions to improve the app" })
      .elements(),
  ).toHaveLength(0);
});

test("the menu with both switches and a deletion owed has nothing axe finds wrong", async () => {
  const screen = await render(withReplay({ given: true }, { given: false, deleting: true }));
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  await expect.element(screen.getByRole("menu")).toBeVisible();
  expect(await axeViolations(screen.getByRole("menu").element())).toEqual([]);
});
