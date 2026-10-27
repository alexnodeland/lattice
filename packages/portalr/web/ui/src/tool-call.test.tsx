import type { Artifactr } from "@portalr/client";
import { expect, onTestFinished, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { RunSteps, ToolCall, ToolCalls } from "./tool-call";

const tool = (change: Partial<Artifactr.Tool> = {}): Artifactr.Tool => ({
  name: "create_artifact",
  status: "ok",
  args: '{"kind": "note", "data": {"text": "Ship Friday"}}',
  result: "Done: note_1 is now at version 1.",
  argsCut: false,
  resultCut: false,
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
  const [running, done] = calls.getByRole("button", { expanded: false }).elements();
  expect(running?.getAttribute("aria-expanded")).toBe("false");
  await expect.element(calls.getByText("Running")).toBeVisible();
  await expect.element(calls.getByText("Done")).toBeVisible();
  expect(done?.textContent).toContain('"Ship Friday"');
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
  // Formatted once the view has loaded: keys and values apart; Raw is the value as recorded.
  await expect.element(screen.getByText('"Ship Friday"')).toBeVisible();
  await screen.getByRole("button", { name: "Raw" }).click();
  await expect
    .element(
      screen
        .getByRole("region", { name: "The arguments of create_artifact" })
        .getByText('{"kind": "note", "data": {"text": "Ship Friday"}}'),
    )
    .toBeVisible();
  await expect.element(screen.getByText("Done: note_1 is now at version 1.")).toBeVisible();
  await screen.getByRole("button", { name: "Copy the result of create_artifact" }).click();
  expect(written).toHaveBeenCalledWith("Done: note_1 is now at version 1.");
  // Copy copies what is shown: Raw, the value as the run recorded it; Formatted, the JSON indented.
  await screen.getByRole("button", { name: "Copy the arguments of create_artifact" }).click();
  expect(written).toHaveBeenLastCalledWith('{"kind": "note", "data": {"text": "Ship Friday"}}');
  await screen.getByRole("button", { name: "Formatted" }).click();
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
  const trigger = page.elementLocator(
    screen.container.querySelector("[aria-expanded]") as HTMLElement,
  );
  await expect.element(trigger).toHaveFocus();
  await userEvent.keyboard("{Enter}");
  await expect.element(trigger).toHaveAttribute("aria-expanded", "true");
  await userEvent.keyboard(" ");
  await expect.element(trigger).toHaveAttribute("aria-expanded", "false");
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
  const [failed, refused] = screen.getByRole("button", { expanded: false }).elements();
  expect(failed?.textContent).toContain("the disk is full");
  expect(refused?.textContent).toContain("Field required");
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
  await expect.element(screen.getByText("not JSON…").last()).toBeVisible();
  const result = screen.getByRole("region", { name: "The result of create_artifact" }).element();
  expect(result.scrollHeight).toBeGreaterThan(result.clientHeight);
  expect(getComputedStyle(result).overflowY).toBe("auto");
  expect(result.tabIndex).toBe(0); // the keyboard reaches it, to scroll it
});

test("a value the run cut short says so, and one that only ends in an ellipsis doesn't", async () => {
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool({ result: "The first part…", resultCut: true })} />
    </ToolCalls>,
  );
  await screen.getByText("create_artifact").click();
  await expect
    .element(screen.getByText("Cut short: the run keeps the first part of each value."))
    .toBeVisible();
  expect(screen.getByText(/^Cut short/).elements()).toHaveLength(1); // its arguments weren't
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

const steps = (statuses: readonly string[]): (readonly [string, Artifactr.Tool])[] =>
  statuses.map((status, at) => [`call_${at}`, tool({ name: `step_${at}`, status, seq: at })]);

test("a run's several calls are one group: its count and how it goes, open while it runs with the newest step open", async () => {
  const screen = await render(
    <ul>
      <RunSteps tools={steps(["ok", "ok", "called"])} running />
    </ul>,
  );
  const group = screen.getByRole("button", { name: "3 steps" });
  await expect.element(group).toHaveAttribute("aria-expanded", "true");
  await expect.element(screen.getByText("Running step 3 of 3")).toBeVisible();
  const list = screen.getByRole("list", { name: "Steps" });
  // A step's row is its disclosure's button; Copy's name holds the step's name too.
  const rows = list.getByRole("button", { name: /^step_/, expanded: true }).elements();
  expect(rows.map((row) => row.textContent?.includes("step_2"))).toEqual([true]);
  expect(list.getByRole("button", { name: /^step_/, expanded: false }).elements()).toHaveLength(2);
});

test("done, the group is folded and says so; failed, it says that; one call is a row of its own", async () => {
  const screen = await render(
    <ul>
      <RunSteps tools={steps(["ok", "ok"])} running={false} />
      <RunSteps tools={steps(["ok", "error"])} running={false} />
      <RunSteps tools={steps(["ok"])} running={false} />
    </ul>,
  );
  const groups = screen.getByRole("button", { name: "2 steps" }).elements();
  expect(groups).toHaveLength(2);
  for (const group of groups) {
    expect(group.getAttribute("aria-expanded")).toBe("false");
  }
  expect(groups.map((group) => group.textContent?.endsWith("Done"))).toEqual([true, false]);
  expect(groups.map((group) => group.textContent?.endsWith("Failed"))).toEqual([false, true]);
  expect(screen.getByRole("button", { name: "1 steps" }).elements()).toHaveLength(0);
  expect(screen.getByRole("button", { name: /^step_0/, expanded: false }).elements()).toHaveLength(
    1,
  );
});

test("a folded group opens from the keyboard to its steps", async () => {
  const screen = await render(
    <ul>
      <RunSteps tools={steps(["ok", "ok"])} running={false} />
    </ul>,
  );
  const group = screen.getByRole("button", { name: "2 steps" });
  group.element().focus();
  await userEvent.keyboard("{Enter}");
  await expect.element(group).toHaveAttribute("aria-expanded", "true");
  await expect.element(screen.getByRole("list", { name: "Steps" })).toBeVisible();
});

test("a group folds as its run ends, says Working between calls, and keeps its count as calls arrive", async () => {
  const screen = await render(
    <ToolCalls>
      <RunSteps tools={steps(["ok"])} running />
    </ToolCalls>,
  );
  await screen.rerender(
    <ToolCalls>
      <RunSteps tools={steps(["ok", "ok"])} running />
    </ToolCalls>,
  );
  const group = screen.getByRole("button", { name: "2 steps" });
  await expect.element(group).toHaveAttribute("aria-expanded", "true");
  await expect.poll(() => group.element().textContent).toContain("Working");
  await screen.rerender(
    <ToolCalls>
      <RunSteps tools={steps(["ok", "ok"])} running={false} />
    </ToolCalls>,
  );
  await expect.element(group).toHaveAttribute("aria-expanded", "false");
  await expect.poll(() => group.element().textContent).toContain("Done");
});

test("the formatted view lays out JSON, shows a string's lines as a block, and code as code", async () => {
  const html = "<!doctype html>\n<html>\n<body>Hi</body>\n</html>";
  const args = JSON.stringify({
    title: "Hello",
    html,
    lines: "one\ntwo",
    n: 3,
    ok: true,
    none: null,
    tags: ["a", "b"],
    empty: {},
  });
  onTestFinished(() => localStorage.removeItem("portalr:tool-call-view"));
  const screen = await render(
    <ToolCalls>
      <ToolCall key="app" tool={tool({ name: "create_app", args })} />
    </ToolCalls>,
  );
  await screen.getByText("create_app").click();
  const toggle = screen.getByRole("group", { name: "View of the arguments of create_app" });
  await expect
    .element(toggle.getByRole("button", { name: "Formatted" }))
    .toHaveAttribute("aria-pressed", "true");
  await expect
    .element(toggle.getByRole("button", { name: "Raw" }))
    .toHaveAttribute("aria-pressed", "false");
  // The toggle sits in the header, outside the box that scrolls.
  const region = screen.getByRole("region", { name: "The arguments of create_app" });
  expect(region.element().contains(toggle.element())).toBe(false);
  // The HTML is a code block, its lines real, labelled by its language, and never run.
  await expect.element(region.getByText("html", { exact: true })).toBeVisible();
  expect(region.element().querySelector("body")).toBeNull();
  const block = region.getByText("html", { exact: true }).element().closest("div")?.parentElement;
  expect(block?.querySelector("pre")?.textContent).toBe(html);
  await expect.element(region.getByRole("button", { name: "Copy this html value" })).toBeVisible();
  // One region takes the focus: the block inside it is no region, nor tab stop, of its own.
  expect(region.element().querySelectorAll("section, [role=region], pre[tabindex]")).toHaveLength(
    0,
  );
  // A string with lines, not code, is a block of its own, wrapped; scalars sit in their lines.
  const lines = region.getByText("one two").element();
  expect(lines.tagName).toBe("PRE");
  expect(getComputedStyle(lines).whiteSpace).toBe("pre-wrap");
  await expect.element(region.getByText('"Hello"')).toBeVisible();
  await expect.element(region.getByText("true")).toBeVisible();
  await expect.element(region.getByText("null")).toBeVisible();
  await expect.element(region.getByText("{}")).toBeVisible();
  // Nothing is wider than its box.
  expect(region.element().scrollWidth).toBeLessThanOrEqual(region.element().clientWidth);
  // Raw is the value as the run recorded it, and the choice is remembered for every call.
  await toggle.getByRole("button", { name: "Raw" }).click();
  await expect.element(region.getByText(/^\{"title":"Hello"/)).toBeVisible();
  expect(localStorage.getItem("portalr:tool-call-view")).toBe("raw");
  await screen.rerender(
    <ToolCalls>
      <ToolCall key="other" tool={tool({ name: "other", args: '{"a": 1}' })} />
    </ToolCalls>,
  );
  await screen.getByText("other").click();
  await expect
    .element(screen.getByRole("button", { name: "Raw" }))
    .toHaveAttribute("aria-pressed", "true");
  await screen.getByRole("button", { name: "Formatted" }).click();
  expect(localStorage.getItem("portalr:tool-call-view")).toBeNull();
});

test("a value cut short is formatted from what parses, and one that isn't JSON has no toggle", async () => {
  const screen = await render(
    <ToolCalls>
      <ToolCall
        tool={tool({
          args: '{"kind": "note", "data": {"text": "Ship Fri',
          argsCut: true,
          result: "Done.",
        })}
      />
    </ToolCalls>,
  );
  await screen.getByText("create_artifact").click();
  await expect.element(screen.getByText('"Ship Fri"')).toBeVisible();
  const note = screen.getByText("Cut short: values at the end may be incomplete.");
  await expect.element(note).toBeVisible();
  const region = screen.getByRole("region", { name: "The arguments of create_artifact" });
  expect(region.element().contains(note.element())).toBe(false);
  await expect
    .element(screen.getByText("Cut short: the run keeps the first part of each value."))
    .toBeVisible();
  expect(
    screen.getByRole("group", { name: "View of the result of create_artifact" }).elements(),
  ).toHaveLength(0);
  await expect.element(screen.getByText("Done.")).toBeVisible();
});

test("each part has its own view, a scalar has none, and a string's direction marks show as escapes", async () => {
  onTestFinished(() => localStorage.removeItem("portalr:tool-call-view"));
  const screen = await render(
    <ToolCalls>
      <ToolCall
        tool={tool({
          args: '{"note": "right\u202eleft", "n": 12345678901234567890}',
          result: '{"ok": true}',
        })}
      />
    </ToolCalls>,
  );
  await screen.getByText("create_artifact").click();
  const args = screen.getByRole("group", { name: "View of the arguments of create_artifact" });
  const result = screen.getByRole("group", { name: "View of the result of create_artifact" });
  await args.getByRole("button", { name: "Raw" }).click();
  await expect
    .element(args.getByRole("button", { name: "Raw" }))
    .toHaveAttribute("aria-pressed", "true");
  await expect
    .element(result.getByRole("button", { name: "Formatted" }))
    .toHaveAttribute("aria-pressed", "true");
  await args.getByRole("button", { name: "Formatted" }).click();
  await expect.element(screen.getByText('"right\\u202eleft"')).toBeVisible();
  await expect.element(screen.getByText(/Long numbers may be rounded here/)).toBeVisible();
  await screen.rerender(
    <ToolCalls>
      <ToolCall key="scalar" tool={tool({ args: "42", result: '"done"' })} />
    </ToolCalls>,
  );
  await screen.getByText("create_artifact").click();
  const shown = screen.getByRole("region", { name: "The arguments of create_artifact" });
  await expect.element(shown.getByText("42")).toBeVisible();
  expect(screen.getByRole("group").elements()).toHaveLength(0);
});

test("a value too heavy to lay out is shown as recorded, with a note", async () => {
  const wide = `[${Array.from({ length: 6000 }, () => "1").join(",")}]`;
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool({ args: wide, result: "ok" })} />
    </ToolCalls>,
  );
  await screen.getByText("create_artifact").click();
  await expect.element(screen.getByText("Too much to format: shown as recorded.")).toBeVisible();
  expect(screen.getByRole("group").elements()).toHaveLength(0);
});

test("Raw shows, and copies, a long number exactly as recorded", async () => {
  onTestFinished(() => localStorage.removeItem("portalr:tool-call-view"));
  const written = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  onTestFinished(() => written.mockRestore());
  const args = '{"id": 12345678901234567}';
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool({ args })} />
    </ToolCalls>,
  );
  await screen.getByText("create_artifact").click();
  const view = screen.getByRole("group", { name: "View of the arguments of create_artifact" });
  await view.getByRole("button", { name: "Raw" }).click();
  const region = screen.getByRole("region", { name: "The arguments of create_artifact" });
  await expect.element(region.getByText(args)).toBeVisible();
  await screen.getByRole("button", { name: "Copy the arguments of create_artifact" }).click();
  expect(written).toHaveBeenLastCalledWith(region.element().textContent);
  expect(written).toHaveBeenLastCalledWith(args);
});
