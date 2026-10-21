/**
 * What ADR-0039 changes, pinned by screenshots: every status badge, the alerts and what is being
 * read, a card and a dialog with their shadows, and a table in each density. Wide, in each scheme;
 * like the gallery's, the baselines are Linux's, made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AccountMenu } from "./account-menu";
import { Button } from "./button";
import { Dialog } from "./dialog";
import { dark } from "./test/colours";
import { Rowed, Sheet } from "./test/galleries";

async function settled() {
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
}

async function matches(name: string, target = page.getByTestId("sheet")) {
  await expect(target).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("the statuses, alerts, what is being read, and the cards", async () => {
  await page.viewport(900, 900);
  onTestFinished(() => page.viewport(414, 896));
  await render(<Sheet />);
  await settled();
  await matches("states-sheet");
});

test("a dialog, with its shadow over a blurred scrim", async () => {
  await page.viewport(900, 600);
  onTestFinished(() => page.viewport(414, 896));
  await render(
    <>
      <Sheet />
      <Dialog
        open
        onOpenChange={() => undefined}
        title="Remove bob from acme?"
        description="bob loses every role in acme."
      >
        <Button variant="danger">Remove</Button>
      </Dialog>
    </>,
  );
  await settled();
  await matches("states-dialog", page.elementLocator(document.body));
});

test("a table in admin's density", async () => {
  await page.viewport(1100, 600);
  onTestFinished(() => page.viewport(414, 896));
  await render(<Rowed ui="admin" />);
  await settled();
  await matches("states-compact", page.elementLocator(document.body));
});

test("a table in the app's density", async () => {
  await page.viewport(1100, 600);
  onTestFinished(() => page.viewport(414, 896));
  await render(<Rowed ui="app" />);
  await settled();
  await matches("states-comfortable", page.elementLocator(document.body));
});

test("the account menu, with colour-blind friendly charts on", async () => {
  await page.viewport(600, 420);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <div className="min-h-screen bg-paper p-4">
      <AccountMenu
        name="Alex Nodeland"
        email="alex@acme.test"
        appearance="system"
        onAppearance={() => undefined}
        colourBlind
        onColourBlind={() => undefined}
        onSignOut={() => undefined}
      />
    </div>,
  );
  await settled();
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  await expect
    .element(screen.getByRole("menuitemcheckbox", { name: "Colour-blind friendly charts" }))
    .toBeVisible();
  await matches("states-account-menu", page.elementLocator(document.body));
});
