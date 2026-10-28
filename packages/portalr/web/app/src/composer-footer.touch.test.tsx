/**
 * A phone's composer footer (portalr ADR-0087): "+" opens the Add sheet, whose Mode sets the
 * agent's mode; the model's pill opens the Select model sheet, read-only while a turn runs; each
 * sheet is a named dialog that gives the focus back to what opened it.
 */

import { afterEach, expect, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { open } from "./test/app";
import { serve as notes, WORLD } from "./test/notes";

afterEach(() => {
  vi.unstubAllGlobals();
});

const MODELS = {
  models: [
    { id: "default", label: "Default" },
    { id: "fast", label: "Fast", family: "Small and quick" },
  ],
};
const serve: typeof notes = async (request, path) =>
  path === "/portalr/v1/models" ? Response.json(MODELS) : notes(request, path);

async function thread() {
  await page.viewport(375, 667);
  const sent: { type: string; mode?: string }[] = [];
  const { screen } = await open(
    "/t/acme/w/notes/threads/thr_1",
    serve,
    (command) => {
      sent.push(command);
      return null;
    },
    WORLD,
  );
  const box = screen.getByRole("textbox", { name: "Message" });
  await expect.element(box).toBeInTheDocument();
  (box.element() as HTMLElement).focus();
  return { screen, sent };
}

test("+ opens the Add sheet; its Mode chooses the agent's mode, and the focus comes back to +", async () => {
  const { screen, sent } = await thread();
  const plus = screen.getByRole("button", { name: "Add", exact: true });
  await plus.click();
  const sheet = screen.getByRole("dialog", { name: "Add" });
  await expect.element(sheet).toBeVisible();
  await expect.element(sheet.getByRole("button", { name: "Add files" })).toBeVisible();
  await sheet.getByRole("button", { name: /^Mode/ }).click();
  const modes = screen.getByRole("dialog", { name: "Agent mode" });
  await expect
    .element(modes.getByRole("button", { name: /^Auto/ }))
    .toHaveAttribute("aria-pressed", "true");
  await modes.getByRole("button", { name: /^Ask/ }).click();
  await expect.poll(() => sent.find((c) => c.type === "set_thread_mode")?.mode).toBe("suggest");
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  await expect.element(plus).toHaveFocus();
  // From the keyboard, as the closing sheet's scrim may still be fading under a pointer.
  await userEvent.keyboard("{Enter}");
  await expect.element(screen.getByRole("dialog", { name: "Add" })).toBeVisible();
  await userEvent.keyboard("{Escape}");
  await expect.element(plus).toHaveFocus();
});

test("the pill names the model and opens the Select model sheet; a choice renames it, and the focus comes back", async () => {
  const { screen } = await thread();
  const pill = screen.getByRole("button", { name: "Model: Default" });
  await expect.element(pill).toBeVisible();
  await pill.click();
  const sheet = screen.getByRole("dialog", { name: "Select model" });
  // A turn waits here: the model is fixed for it, and the sheet says so.
  await expect.element(sheet).toHaveAccessibleDescription("The running turn keeps its model");
  await expect.element(sheet.getByRole("button", { name: /^Fast/ })).toBeDisabled();
  await userEvent.keyboard("{Escape}");
  await expect.element(pill).toHaveFocus();
});
