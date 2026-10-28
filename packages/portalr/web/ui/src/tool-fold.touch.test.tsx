/**
 * A group of a run's calls on a phone (portalr ADR-0055): its line opens a sheet of the calls,
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
  await sheet.getByRole("button", { name: "Back to the calls" }).click();
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
      <RunSteps tools={[["resized_1", tool("fetch", "ok", '{"url": "a"}', "ok")]]} />
    </ul>,
  );
  await page.viewport(393, 852);
  await screen.getByRole("button", { name: "Fetched a page: 1 tool call" }).click();
  await expect.element(screen.getByRole("dialog", { name: "Fetched a page" })).toBeVisible();
  expect(document.querySelectorAll("li > ol[aria-label='Tool calls']")).toHaveLength(0);
});
