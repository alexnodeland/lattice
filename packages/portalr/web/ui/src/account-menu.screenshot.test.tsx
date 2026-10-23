/**
 * The account menu with product analytics' switch, pinned by screenshots (lattice RFC-0008): off,
 * on, and off with a deletion still to be done, in each scheme. The baselines are Linux's, made
 * in CI.
 */

import { expect, onTestFinished, test, vi } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { AccountMenu, type AnalyticsAnswer } from "./account-menu";
import { dark } from "./test/colours";

const GUIDE = "https://lattice.example/portalr/guides/privacy/";

async function opened(analytics: AnalyticsAnswer) {
  await page.viewport(900, 700);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <AccountMenu
      name="Alex Nodeland"
      appearance="system"
      onAppearance={vi.fn()}
      colourBlind={false}
      onColourBlind={vi.fn()}
      analytics={analytics}
      onSignOut={vi.fn()}
    />,
  );
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await screen.getByRole("button", { name: "Account: Alex Nodeland" }).click();
  await expect.element(page.getByRole("menu")).toBeVisible();
  await commands.pointerAway();
}

async function matches(name: string) {
  await expect(page.getByRole("menu")).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("the account menu, sharing off", async () => {
  await opened({ given: false, onAnswer: vi.fn(), guide: GUIDE });
  await matches("account-analytics-off");
});

test("the account menu, sharing on", async () => {
  await opened({ given: true, onAnswer: vi.fn(), guide: GUIDE });
  await matches("account-analytics-on");
});

test("the account menu, sharing off and what was shared still being deleted", async () => {
  await opened({ given: false, onAnswer: vi.fn(), deleting: true, guide: GUIDE });
  await matches("account-analytics-deleting");
});
