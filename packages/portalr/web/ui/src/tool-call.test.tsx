import type { Artifactr } from "@portalr/client";
import { expect, onTestFinished, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { ToolCall, ToolCalls } from "./tool-call";

const tool = (change: Partial<Artifactr.Tool> = {}): Artifactr.Tool => ({
  name: "create_artifact",
  status: "ok",
  args: '{"kind": "note", "data": {"text": "Ship Friday"}}',
  result: "Done: note_1 is now at version 1.",
  seq: 1,
  ...change,
});

test("closed, a call says its name, how it is going and a line of its arguments", async () => {
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool({ status: "called", result: "" })} />
      <ToolCall tool={tool({ name: "read_artifact" })} />
    </ToolCalls>,
  );
  const calls = screen.getByRole("list", { name: "Tools" });
  const [running, done] = calls.getByRole("group").elements();
  expect(running?.hasAttribute("open")).toBe(false);
  await expect.element(calls.getByText("Running")).toBeVisible();
  await expect.element(calls.getByText("Done")).toBeVisible();
  expect(done?.querySelector("summary")?.textContent).toContain('"Ship Friday"');
  await expect.element(calls.getByText("Arguments").first()).not.toBeVisible();
});

test("open, it shows its arguments indented and what it returned, each to copy", async () => {
  const written = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  onTestFinished(() => written.mockRestore());
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool()} />
    </ToolCalls>,
  );
  await screen.getByText("create_artifact").click();
  await expect
    .element(screen.getByText(/^\{\n {2}"kind": "note",\n {2}"data": \{\n {4}"text"/))
    .toBeVisible();
  await expect.element(screen.getByText("Done: note_1 is now at version 1.")).toBeVisible();
  await screen.getByRole("button", { name: "Copy the result of create_artifact" }).click();
  expect(written).toHaveBeenCalledWith("Done: note_1 is now at version 1.");
  await screen.getByRole("button", { name: "Copy the arguments of create_artifact" }).click();
  expect(written).toHaveBeenLastCalledWith(
    JSON.stringify({ kind: "note", data: { text: "Ship Friday" } }, null, 2),
  );
});

test("the keyboard opens and closes a call", async () => {
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool()} />
    </ToolCalls>,
  );
  await userEvent.tab();
  const details = screen.getByRole("group").element();
  expect(document.activeElement).toBe(details.querySelector("summary"));
  await userEvent.keyboard("{Enter}");
  expect(details.hasAttribute("open")).toBe(true);
  await userEvent.keyboard(" ");
  expect(details.hasAttribute("open")).toBe(false);
});

test("a failed or refused call says why where it is closed, and under its own name open", async () => {
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool({ status: "error", result: "RuntimeError: the disk is full" })} />
      <ToolCall
        tool={tool({ name: "draft_rule", status: "retry", result: "rule\n  Field required" })}
      />
    </ToolCalls>,
  );
  await expect.element(screen.getByText("Failed")).toBeVisible();
  await expect.element(screen.getByText("Refused")).toBeVisible();
  const [failed, refused] = screen.getByRole("group").elements();
  expect(failed?.querySelector("summary")?.textContent).toContain("the disk is full");
  expect(refused?.querySelector("summary")?.textContent).toContain("Field required");
  await screen.getByText("draft_rule").click();
  await expect.element(screen.getByText("Why it was refused")).toBeVisible();
  await screen.getByText("create_artifact").click();
  await expect.element(screen.getByText("Error", { exact: true })).toBeVisible();
});

test("a long value is capped, and scrolls; a value that isn't JSON is shown as it was", async () => {
  const long = Array.from({ length: 80 }, (_, line) => `line ${line}`).join("\n");
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool({ args: "not JSON…", result: long })} />
    </ToolCalls>,
  );
  await screen.getByText("create_artifact").click();
  await expect.element(screen.getByRole("group").getByText("not JSON…").last()).toBeVisible();
  const result = screen.getByText(/line 79/).element();
  expect(result.scrollHeight).toBeGreaterThan(result.clientHeight);
  expect(getComputedStyle(result).overflowY).toBe("auto");
});

test("a status the run didn't name is said as it was", async () => {
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool({ status: "skipped", args: "" })} />
    </ToolCalls>,
  );
  await expect.element(screen.getByText("skipped")).toBeVisible();
  await screen.getByText("create_artifact").click();
  await expect.element(screen.getByText("{}", { exact: true })).toBeVisible();
});
