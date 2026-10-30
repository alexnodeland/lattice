/**
 * The chat's look, pinned by screenshots (portalr ADR-0053): the reader's messages and the
 * agent's on their sides, a run's tool calls, folded and opened, the agent's questions, open and
 * answered, a turn that is thinking, and one that failed. Wide and narrow, in each scheme. Like the
 * gallery's, the baselines are Linux's, made in CI.
 */

import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { dark } from "./test/colours";
import { Ended, Thread } from "./test/galleries";

/** Lay out what to shoot at a width, with the faces loaded and the pointer off it. */
async function shown(width: number, what: React.ReactNode) {
  await page.viewport(width, 1800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(what);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
  return screen;
}

async function matches(name: string) {
  await expect(page.getByTestId("chat")).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("a thread: sides, questions, tool calls with one open, and thinking, wide", async () => {
  const screen = await shown(900, <Thread />);
  // The quiet line opened, a failed call among its calls.
  await screen.getByRole("button", { name: /· 1 failed: (.+, )?2 tool calls$/ }).click();
  await matches("chat-wide");
});

test("the same thread, narrow", async () => {
  await shown(390, <Thread />);
  await matches("chat-narrow");
});

test("questions answered, and a failed turn", async () => {
  await shown(900, <Ended />);
  await matches("chat-ended");
});
