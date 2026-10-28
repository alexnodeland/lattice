/**
 * A phone's composer footer (portalr ADR-0087): "+" opens the Add sheet, whose Mode is a radio
 * group of Auto and Ask behind a Back; the model's pill opens Select model, a radio group fixed
 * while a turn runs; each sheet is a named dialog that gives the focus back to what opened it.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open } from "./test/app";
import { serve as notes, WORLD } from "./test/notes";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const MODELS = {
  models: [
    { id: "default", label: "Default" },
    { id: "fast", label: "Fast" },
    { id: "other", label: "Other", family: "Not a description" },
  ],
};
const serve: typeof notes = async (request, path) =>
  path === "/portalr/v1/models" ? Response.json(MODELS) : notes(request, path);

const at = (seq: number, event: unknown) => ({
  type: "event",
  seq,
  id: `evt_${seq}`,
  ts: "2026-10-27T09:00:00Z",
  workspace_id: "notes",
  actor: { kind: "user", id: "alice" },
  event,
});
/** A thread with nothing running: its model may be chosen. */
const QUIET = [at(1, { type: "thread_created", thread_id: "thr_q", title: "Quiet" })];

async function thread(path = "/t/acme/w/notes/threads/thr_1", log: unknown = WORLD) {
  await page.viewport(375, 667);
  const sent: { type: string; mode?: string; model?: string; content?: string }[] = [];
  const { screen } = await open(
    path,
    serve,
    (command) => {
      sent.push(command);
      return null;
    },
    log as typeof WORLD,
  );
  const box = screen.getByRole("textbox", { name: "Message" });
  await expect.element(box).toBeInTheDocument();
  // The footer is there to tap once its + is: what a click on it would otherwise race.
  const plus = screen.getByRole("button", { name: "Add", exact: true });
  await expect.element(plus).toBeVisible();
  (box.element() as HTMLElement).focus();
  return { screen, sent, box, plus };
}

/** + tapped, then Add's Mode: the Mode sheet, its Back focused, and its radio group. */
async function inMode() {
  const opened = await thread();
  const { screen, plus } = opened;
  await plus.click();
  const sheet = screen.getByRole("dialog", { name: "Add" });
  await expect.element(sheet).toBeVisible();
  await sheet.getByRole("button", { name: /^Mode/ }).click();
  const modes = screen.getByRole("dialog", { name: "Agent mode" });
  await expect.element(modes.getByRole("button", { name: "Back to Add" })).toHaveFocus();
  return { ...opened, group: modes.getByRole("radiogroup", { name: "Agent mode" }) };
}

test("+ opens Add, whose Mode is a radio group behind Back, and the arrows choose", async () => {
  const { sent, group } = await inMode();
  await expect.element(group.getByRole("radio", { name: "Auto" })).toBeChecked();
  await expect
    .element(group.getByRole("radio", { name: "Ask" }))
    .toHaveAccessibleDescription("The assistant proposes changes for you to accept.");
  // The arrows choose, as a radio group's do.
  (group.getByRole("radio", { name: "Auto" }).element() as HTMLElement).focus();
  await userEvent.keyboard("{ArrowDown}");
  await expect.poll(() => sent.find((c) => c.type === "set_thread_mode")?.mode).toBe("suggest");
});

test("in Mode, Escape goes back to Add first, then closes, and the focus follows", async () => {
  const { screen, plus } = await inMode();
  // Escape goes back to Add, to the Mode row; again, it closes, and the focus is +'s.
  await userEvent.keyboard("{Escape}");
  await expect
    .element(screen.getByRole("dialog", { name: "Add" }).getByRole("button", { name: /^Mode/ }))
    .toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  await expect.element(plus).toHaveFocus();
});

test("Add files closes the sheet and opens the system's chooser, whose files go to the uploader", async () => {
  const { screen, plus } = await thread();
  const clicked = vi.spyOn(HTMLInputElement.prototype, "click").mockImplementation(() => undefined);
  await plus.click();
  await screen
    .getByRole("dialog", { name: "Add" })
    .getByRole("button", { name: "Add files" })
    .click();
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  await expect
    .poll(() => clicked.mock.instances.some((input) => (input as HTMLInputElement).type === "file"))
    .toBe(true);
});

test("the pill opens Select model, a radio group of what the workspace allows, each a finger's size; a choice is sent with the next message, and the default never", async () => {
  const { screen, sent, box } = await thread("/t/acme/w/notes/threads/thr_q", {
    artifactrLog: QUIET,
  });
  const pill = screen.getByRole("button", { name: "Model: Default" });
  await expect.element(pill, { timeout: 10_000 }).toBeVisible();
  expect(pill.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  await pill.click();
  const sheet = screen.getByRole("dialog", { name: "Select model" });
  const group = sheet.getByRole("radiogroup", { name: "Models" });
  await expect.element(group.getByRole("radio", { name: "Default" })).toBeChecked();
  await expect
    .element(group.getByRole("radio", { name: "Fast" }))
    .toHaveAccessibleDescription("Small and quick");
  // What isn't known is not said: no line from a family.
  expect(sheet.element().textContent).not.toContain("Not a description");
  for (const radio of group.getByRole("radio").elements()) {
    expect(radio.getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  }
  await group.getByRole("radio", { name: "Fast" }).click();
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("button", { name: "Model: Fast" })).toHaveFocus();
  await box.fill("Hello");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.poll(() => sent.find((c) => c.type === "post_message")?.model).toBe("fast");
});

test("while a turn runs the model is fixed for it: the sheet says so, and its choices can't be taken", async () => {
  const { screen } = await thread();
  const pill = screen.getByRole("button", { name: "Model: Default" });
  await expect.element(pill, { timeout: 10_000 }).toBeVisible();
  await pill.click();
  const sheet = screen.getByRole("dialog", { name: "Select model" });
  await expect.element(sheet).toHaveAccessibleDescription("Fixed for this turn");
  await expect.element(sheet.getByRole("radio", { name: "Fast" })).toBeDisabled();
  await userEvent.keyboard("{Escape}");
  await expect.element(pill).toHaveFocus();
});

test("written, Send stands where Answer stood: never both", async () => {
  const { screen, box } = await thread();
  const bar = () => document.querySelector("[data-thumb-bar]") as HTMLElement | null;
  await expect.poll(() => bar()?.checkVisibility()).toBe(true);
  await box.fill("Hello");
  await expect.element(screen.getByRole("button", { name: "Send" })).toBeVisible();
  expect(bar()?.checkVisibility() ?? false).toBe(false);
  await box.fill("");
  await expect.poll(() => bar()?.checkVisibility()).toBe(true);
  expect(
    (
      screen.getByRole("button", { name: "Send" }).query() as HTMLElement | null
    )?.checkVisibility() ?? false,
  ).toBe(false);
});
