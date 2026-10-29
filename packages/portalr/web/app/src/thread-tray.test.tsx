/**
 * What waits for the reader in a thread (portalr ADR-0092): one tray in the composer's dock, shut
 * to a line where several wait, and opened by whatever reaches into it: "Go to the question", a
 * link from Needs you, a hash; with an approval beside it, which keeps its own card.
 */

import { afterEach, expect, test } from "vitest";
import { open } from "./test/app";
import { ASKING, pausedOn, serve, TOUR } from "./test/tour";

const THREAD = "/t/acme/w/notes/threads/thr_1";

afterEach(() => {
  history.replaceState(null, "", location.pathname);
});

const tray = () => document.querySelector("[aria-label='Waiting for you']");

test("a question and a proposal waiting are one line over the composer, opened by Go to the question", async () => {
  const { screen } = await open(THREAD, serve, () => null, { artifactrLog: ASKING });
  const line = screen.getByRole("button", { name: /2 waiting for you/ });
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  // Said by what they are, not "a question" twice.
  expect(line.element().textContent).toContain("Which week should the note cover?");
  expect(line.element().textContent).toContain("Add a closing line");
  expect(document.querySelector("[data-composer-dock]")?.contains(tray())).toBe(true);
  // The turn's strip, above them, takes the reader to the question: the tray opens at it.
  await screen.getByRole("button", { name: "Go to the question" }).click();
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  await expect.element(screen.getByText("Which week should the note cover?").last()).toBeVisible();
  await expect.poll(() => document.activeElement?.closest("#request-q1") !== null).toBe(true);
  expect(document.activeElement?.closest("[data-tray]")).not.toBeNull();
});

test("a link to a request, as Needs you gives, opens the tray at it", async () => {
  const { screen } = await open(`${THREAD}#request-q1`, serve, () => null, {
    artifactrLog: ASKING,
  });
  const line = screen.getByRole("button", { name: /2 waiting for you/ });
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  await expect.poll(() => document.activeElement?.closest("#request-q1") !== null).toBe(true);
});

test("a proposal waiting is announced, politely, where it sits", async () => {
  const { screen } = await open(THREAD, serve, () => null, { artifactrLog: TOUR });
  // One thing waiting: shown whole, with no line, and said once.
  await expect
    .element(screen.getByRole("region", { name: "Proposal: Add a closing line" }))
    .toBeVisible();
  expect(
    [...document.querySelectorAll("[role=status]")].some(
      (status) => status.textContent === "1 waiting for you",
    ),
  ).toBe(true);
});

test("an approval keeps its own card, beside the tray: both are in reach", async () => {
  const { screen } = await open(THREAD, serve, () => null, {
    artifactrLog: pausedOn([
      { kind: "approval", tool_call_id: "a1", tool_name: "send_note", args: { to: "a@b.test" } },
    ]),
  });
  const approve = screen.getByRole("button", { name: "Approve" });
  await expect.element(approve).toBeVisible();
  // The tray holds the proposal and no approval; the approval's card isn't in the tray.
  await expect
    .element(screen.getByRole("region", { name: "Proposal: Add a closing line" }))
    .toBeVisible();
  expect(tray()?.contains(approve.element())).toBe(false);
  await expect.element(screen.getByRole("button", { name: "Accept" })).toBeVisible();
});
