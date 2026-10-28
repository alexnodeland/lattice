/**
 * A group of a run's calls on a phone (portalr ADR-0053): its line opens a sheet of the calls,
 * which goes on to a call's detail and back, and closes to the line.
 */

import type { Artifactr } from "@portalr/client";
import { expect, onTestFinished, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { axeViolations } from "./test/axe";
import { RunSteps } from "./tool-call";

const tool = (name: string, status: string, args: string, result: string): Artifactr.Tool => ({
  name,
  status,
  args,
  result,
  argsCut: false,
  resultCut: false,
  seq: 1,
});

test("the line opens a sheet of the calls, which goes on to a call and back, and closes to the line", async () => {
  const written = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  onTestFinished(() => written.mockRestore());
  const screen = await render(
    <ul>
      <RunSteps
        tools={[
          [
            "sheet_1",
            tool("update_app", "ok", '{"title": "Timer"}', "Done: app_1 is now at version 2."),
          ],
          ["sheet_2", tool("read_artifact", "error", '{"id": "x"}', "Not found")],
        ]}
      />
    </ul>,
  );
  const line = screen.getByRole("button", {
    name: "Updated an app, read an artifact · 1 failed: 2 tool calls",
  });
  expect(line.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
  expect(line.element().getAttribute("aria-haspopup")).toBe("dialog");
  await line.click();
  await expect
    .element(screen.getByRole("dialog", { name: "Updated an app, read an artifact · 1 failed" }))
    .toBeVisible();
  const sheet = screen.getByRole("dialog");
  const list = sheet.getByRole("list", { name: "Tool calls" });
  await expect.element(list.getByText("Timer")).toBeVisible();
  await expect.element(list.getByText("Not found")).toBeVisible();
  expect(await axeViolations(sheet.element())).toEqual([]);
  await list.getByRole("button", { name: /^Updated an app/ }).click();
  await expect.element(screen.getByRole("button", { name: "Back to the calls" })).toHaveFocus();
  await expect.element(screen.getByRole("dialog", { name: "Updated an app" })).toBeVisible();
  await expect.element(sheet.getByText("update_app", { exact: true })).toBeVisible();
  await sheet.getByRole("button", { name: "Copy the result of update_app" }).click();
  expect(written).toHaveBeenLastCalledWith("Done: app_1 is now at version 2.");
  expect(await axeViolations(sheet.element())).toEqual([]);
  // Escape from a call's detail goes back to the list, not out of the sheet.
  await userEvent.keyboard("{Escape}");
  await expect.element(list.getByRole("button", { name: /^Updated an app/ })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  await expect.element(sheet).not.toBeInTheDocument();
  await expect.element(line).toHaveFocus();
});

test("on a phone a tap opens the sheet, never the unfurl, even just after the window changed", async () => {
  onTestFinished(() => page.viewport(414, 896));
  await page.viewport(900, 800);
  const screen = await render(
    <ul>
      <RunSteps tools={[["resized_1", tool("view_page", "ok", '{"url": "a"}', "ok")]]} />
    </ul>,
  );
  await page.viewport(393, 852);
  await screen.getByRole("button", { name: "Looked at a page: 1 tool call" }).click();
  await expect.element(screen.getByRole("dialog", { name: "Looked at a page" })).toBeVisible();
  expect(document.querySelectorAll("li > ol[aria-label='Tool calls']")).toHaveLength(0);
});

test("dragged down from a call's detail, the sheet opens again at its list", async () => {
  const screen = await render(
    <ul>
      <RunSteps
        tools={[
          ["drag_1", tool("read_artifact", "ok", '{"title": "Q3"}', "28 rows")],
          ["drag_2", tool("draw", "ok", '{"title": "Flow"}', "ok")],
        ]}
      />
    </ul>,
  );
  const line = screen.getByRole("button", { name: /: 2 tool calls$/ });
  await line.click();
  const dialog = screen.getByRole("dialog");
  await dialog.getByRole("button", { name: /^Read an artifact/ }).click();
  await expect.element(screen.getByRole("button", { name: "Back to the calls" })).toBeVisible();
  await expect.poll(() => dialog.element().hasAttribute("data-sheet-drag")).toBe(true);
  const handle = dialog.element().querySelector("[data-sheet-handle]") as HTMLElement;
  const tall = dialog.element().getBoundingClientRect().height;
  const at = (type: string, y: number) =>
    new PointerEvent(type, { bubbles: true, clientY: y, pointerId: 1, pointerType: "touch" });
  handle.dispatchEvent(at("pointerdown", 500));
  dialog.element().dispatchEvent(at("pointermove", 500 + tall * 0.5));
  dialog.element().dispatchEvent(at("pointerup", 500 + tall * 0.5));
  await expect.element(dialog).not.toBeInTheDocument();
  await line.click();
  await expect
    .element(screen.getByRole("dialog").getByRole("list", { name: "Tool calls" }))
    .toBeVisible();
});

test("a failed call's line says why without the ids in it", async () => {
  const screen = await render(
    <ul>
      <RunSteps
        tools={[
          ["ids_1", tool("update_app", "error", "{}", "No app app_9: the id names nothing.")],
        ]}
      />
    </ul>,
  );
  await screen.getByRole("button", { name: /: 1 tool call$/ }).click();
  const list = screen.getByRole("dialog").getByRole("list", { name: "Tool calls" });
  await expect.element(list.getByText("No app : the id names nothing.")).toBeVisible();
  expect(list.element().textContent).not.toMatch(/app_\d/);
});

test("turned wide with its sheet open, the sheet stays the one way in, and turned back so does an unfurl", async () => {
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(
    <ul>
      <RunSteps tools={[["turn_1", tool("draw", "ok", '{"title": "Flow"}', "ok")]]} />
    </ul>,
  );
  const line = screen.getByRole("button", { name: /: 1 tool call$/ });
  const button = line.element();
  await line.click();
  await page.viewport(900, 800);
  await expect.element(screen.getByRole("dialog")).toBeVisible();
  expect(document.querySelectorAll("li > ol[aria-label='Tool calls']")).toHaveLength(0);
  expect(button.getAttribute("aria-haspopup")).toBe("dialog");
  await userEvent.keyboard("{Escape}");
  await expect.element(screen.getByRole("dialog")).not.toBeInTheDocument();
  // Wide now, a tap unfurls; turned back to a phone, the unfurl stays, named as what it controls.
  await line.click();
  const list = screen.getByRole("list", { name: "Tool calls" });
  await expect.element(list).toBeVisible();
  await page.viewport(393, 852);
  await expect.element(list).toBeVisible();
  expect(button.getAttribute("aria-controls")).toBe(list.element().id);
  expect(document.querySelectorAll("[role=dialog]")).toHaveLength(0);
});
