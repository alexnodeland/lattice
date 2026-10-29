import type { Artifactr } from "@portalr/client";
import { expect, onTestFinished, test, vi } from "vitest";
import { commands, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { axeViolations } from "./test/axe";
import { RunSteps } from "./tool-call";
import { doneLabel, doneLabels, foldSummary } from "./tool-fold";

const tool = (name: string, status = "ok", args = "{}", result = "Done."): Artifactr.Tool => ({
  name,
  status,
  args,
  result,
  argsCut: false,
  resultCut: false,
  seq: 1,
});

let group = 0;
/** Calls under ids no other test's group has, as which groups were opened is kept by id. */
const calls = (...tools: Artifactr.Tool[]) => {
  group += 1;
  return tools.map((each, at) => [`fold${group}_${at}`, each] as const);
};

test("the calls are said in plain words, counted, in the order first called", () => {
  expect(doneLabel([tool("create_app")])).toBe("Made an app");
  expect(doneLabel([tool("update_app")])).toBe("Updated an app");
  expect(doneLabel([tool("create_app"), tool("read_artifact"), tool("read_artifact")])).toBe(
    "Made an app, read 2 artifacts",
  );
  expect(doneLabel([tool("search_web"), tool("mcp_thing"), tool("view_page")])).toBe(
    "Used 2 tools, looked at a page",
  );
});

test("tools that say the same are counted together, and a name on Object's prototype is a tool", () => {
  expect(doneLabel([tool("draw"), tool("draw_mermaid")])).toBe("Drew 2 diagrams");
  expect(doneLabel([tool("edit_text"), tool("edit_artifact")])).toBe("Edited 2 artifacts");
  for (const name of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
    expect(doneLabel([tool(name)])).toBe("Used a tool");
  }
});

/** The calls of each tool, in turn: a name, and how many times it was called. */
const run = (...each: readonly (readonly [string, number])[]) =>
  each.flatMap(([name, n]) => Array.from({ length: n }, () => tool(name)));

test("a run's calls are counted by kind, as the owner reads them, with the plurals right", () => {
  expect(doneLabel(run(["create_artifact", 2], ["mystery", 3], ["create_app", 1]))).toBe(
    "Made 2 artifacts, used 3 tools, made an app",
  );
  expect(doneLabel(run(["read_artifact", 1]))).toBe("Read an artifact");
  expect(doneLabel(run(["find_commands", 1], ["list_artifacts", 1]))).toBe(
    "Looked up commands, looked through the artifacts",
  );
});

test("a line short of room may say the first two kinds, then the first, each whole, with the rest counted", () => {
  const four = run(
    ["find_commands", 1],
    ["edit_native", 1],
    ["archive_artifact", 1],
    ["mystery", 2],
  );
  expect(doneLabels(four)).toEqual([
    "Looked up commands, edited a file, archived an artifact, used 2 tools",
    "Looked up commands, edited a file and 3 more",
    "Looked up commands and 4 more",
  ]);
  // Two kinds: both, or the first and the calls of the other.
  expect(doneLabels(run(["create_artifact", 2], ["mystery", 3]))).toEqual([
    "Made 2 artifacts, used 3 tools",
    "Made 2 artifacts and 3 more",
  ]);
  // One kind has nothing to count after it, and no shorter way to say it.
  expect(doneLabels(run(["draw", 30]))).toEqual(["Drew 30 diagrams"]);
  expect(doneLabels(run(["read_artifact", 1]))).toEqual(["Read an artifact"]);
  // Three kinds, the first long.
  expect(doneLabels(run(["comment_on_item", 1], ["mystery", 1], ["draw", 1]))).toEqual([
    "Commented on an item, used a tool, drew a diagram",
    "Commented on an item, used a tool and 1 more",
    "Commented on an item and 2 more",
  ]);
  expect(doneLabel(four)).toBe(doneLabels(four)[0]);
});

test("a line's shorter ways count the calls of the kinds left out, not the kinds", () => {
  const many = run(["find_commands", 2], ["edit_native", 1], ["archive_artifact", 3], ["x", 4]);
  expect(doneLabels(many)).toEqual([
    "Looked up commands, edited a file, archived 3 artifacts, used 4 tools",
    "Looked up commands, edited a file and 7 more",
    "Looked up commands and 8 more",
  ]);
});

test("while a call runs the line says it is doing it; a failure is counted", () => {
  expect(foldSummary([tool("read_artifact"), tool("create_app", "called")])).toEqual({
    labels: ["Making an app…"],
    failed: 0,
    running: true,
  });
  expect(foldSummary([tool("update_app", "error")]).failed).toBe(1);
});

test("a group is one quiet line, closed, named by what it did and its count", async () => {
  const screen = await render(
    <ul>
      <RunSteps tools={calls(tool("update_app"), tool("create_app"))} />
    </ul>,
  );
  const line = screen.getByRole("button", { name: "Updated an app, made an app: 2 tool calls" });
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  expect(line.element().textContent).not.toContain("update_app");
  expect(screen.getByRole("list", { name: "Tool calls" }).elements()).toHaveLength(0);
  expect(await axeViolations(screen.container)).toEqual([]);
});

test("a long line says the longest way it has that fits, whole, with the whole in its name", async () => {
  const many = ["create_app", "read_artifact", "draw", "fetch", "send_message", "post_notice"];
  const screen = await render(
    <div className="w-60">
      <ul>
        <RunSteps tools={calls(...many.map((name) => tool(name)))} />
      </ul>
    </div>,
  );
  const words = screen.container.querySelector("button span.truncate") as HTMLElement;
  await expect.poll(() => words.textContent).toBe("Made an app and 5 more");
  expect(words.scrollWidth).toBeLessThanOrEqual(words.clientWidth);
  await expect
    .element(screen.getByRole("button", { name: /posted a notice: 6 tool calls$/ }))
    .toBeVisible();
});

test("where not even its shortest way fits, a line is cut by an ellipsis, with the whole in its name", async () => {
  const screen = await render(
    <div className="w-24">
      <ul>
        <RunSteps tools={calls(tool("comment_on_item"), tool("draw"))} />
      </ul>
    </div>,
  );
  const words = screen.container.querySelector("button span.truncate") as HTMLElement;
  await expect.poll(() => words.textContent).toBe("Commented on an item and 1 more");
  expect(words.scrollWidth).toBeGreaterThan(words.clientWidth);
  expect(getComputedStyle(words).textOverflow).toBe("ellipsis");
  await expect
    .element(
      screen.getByRole("button", { name: "Commented on an item, drew a diagram: 2 tool calls" }),
    )
    .toBeVisible();
});

test("the line says its longest way again as its box grows", async () => {
  const screen = await render(
    <div id="box" className="w-40">
      <ul>
        <RunSteps tools={calls(tool("create_app"), tool("read_artifact"))} />
      </ul>
    </div>,
  );
  const words = screen.container.querySelector("button span.truncate") as HTMLElement;
  await expect.poll(() => words.textContent).toBe("Made an app and 1 more");
  (screen.container.querySelector("#box") as HTMLElement).style.width = "30rem";
  await expect.poll(() => words.textContent).toBe("Made an app, read an artifact");
});

test("Enter and Space unfurl the calls beneath, the focus staying on the line", async () => {
  const screen = await render(
    <ul>
      <RunSteps tools={calls(tool("read_artifact", "ok", '{"title": "Q3"}'))} />
    </ul>,
  );
  const line = screen.getByRole("button", { name: "Read an artifact: 1 tool call" });
  line.element().focus();
  await userEvent.keyboard("{Enter}");
  await expect.element(line).toHaveAttribute("aria-expanded", "true");
  const list = screen.getByRole("list", { name: "Tool calls" });
  expect(line.element().getAttribute("aria-controls")).toBe(list.element().id);
  await expect.element(list.getByText("Q3")).toBeVisible();
  await expect.element(line).toHaveFocus();
  await userEvent.keyboard(" ");
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
});

test("open, each call goes on to its detail and its raw form, Copy working", async () => {
  const written = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  onTestFinished(() => {
    written.mockRestore();
    localStorage.removeItem("portalr:tool-call-view");
  });
  const screen = await render(
    <ul>
      <RunSteps tools={calls(tool("create_app", "ok", '{"title": "Timer"}'))} />
    </ul>,
  );
  await screen.getByRole("button", { name: /^Made an app: 1 tool call/ }).click();
  await screen.getByRole("button", { name: /^Made an app\s*Timer/ }).click();
  await expect.element(screen.getByText("What it was asked")).toBeVisible();
  await expect.element(screen.getByText("create_app", { exact: true })).toBeVisible();
  await screen.getByRole("button", { name: "Raw" }).first().click();
  await screen.getByRole("button", { name: "Copy the arguments of create_app" }).click();
  expect(written).toHaveBeenLastCalledWith('{"title": "Timer"}');
});

test("a failed call is marked in words, and the group stays closed", async () => {
  const screen = await render(
    <ul>
      <RunSteps tools={calls(tool("update_app", "error", "{}", "The app didn't build"))} />
    </ul>,
  );
  const line = screen.getByRole("button", { name: "Updated an app · 1 failed: 1 tool call" });
  await expect.element(line).toHaveAttribute("aria-expanded", "false");
  expect(line.element().textContent).toContain("1 failed");
});

test("running, it shimmers unless motion is reduced; new calls keep it as the reader left it, and its end is said once", async () => {
  onTestFinished(() => commands.reduceMotion(true));
  const still = await render(
    <ul>
      <RunSteps tools={calls(tool("create_app", "called"))} />
    </ul>,
  );
  const shown = (container: HTMLElement) =>
    container.querySelector("button span.truncate") as HTMLElement;
  expect(shown(still.container).textContent).toBe("Making an app…");
  expect(shown(still.container).getAnimations()).toHaveLength(0);
  await still.unmount();
  await commands.reduceMotion(false);
  const first = calls(tool("read_artifact"), tool("create_app", "called"));
  const screen = await render(
    <ul>
      <RunSteps tools={first} running />
    </ul>,
  );
  const words = () => shown(screen.container);
  expect(words().getAnimations()).toHaveLength(1);
  expect(words().style.color).toBe("transparent");
  expect(screen.getByRole("status").element().textContent).toBe("");
  await screen.getByRole("button", { name: "Making an app…: 2 tool calls" }).click();
  const more = [...first, ["more", tool("draw", "called")] as const];
  await screen.rerender(
    <ul>
      <RunSteps tools={more} running />
    </ul>,
  );
  await expect
    .element(screen.getByRole("button", { name: "Drawing a diagram…: 3 tool calls" }))
    .toHaveAttribute("aria-expanded", "true");
  // Between one call's answer and the next, its run still runs: nothing is said, nothing flickers.
  const done = more.map(([id, each]) => [id, { ...each, status: "ok" }] as const);
  await screen.rerender(
    <ul>
      <RunSteps tools={done} running />
    </ul>,
  );
  expect(words().textContent).toBe("Drawing a diagram…");
  expect(words().getAnimations()).toHaveLength(1);
  expect(screen.getByRole("status").element().textContent).toBe("");
  await screen.rerender(
    <ul>
      <RunSteps tools={done} running={false} />
    </ul>,
  );
  expect(words().getAnimations()).toHaveLength(0);
  expect(words().style.color).toBe("");
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("Read an artifact, made an app, drew a diagram");
});

test("which groups were opened is kept as the thread is shown again", async () => {
  const same = calls(tool("view_page"));
  const first = await render(
    <ul>
      <RunSteps tools={same} />
    </ul>,
  );
  await first.getByRole("button", { name: "Looked at a page: 1 tool call" }).click();
  await first.unmount();
  const again = await render(
    <ul>
      <RunSteps tools={same} />
    </ul>,
  );
  await expect
    .element(again.getByRole("button", { name: "Looked at a page: 1 tool call" }))
    .toHaveAttribute("aria-expanded", "true");
});

test("under forced colours a running line has no shimmer", async () => {
  onTestFinished(() => commands.reduceMotion(true));
  await commands.reduceMotion(false);
  const forced = matchMedia("(forced-colors: active)").matches;
  const screen = await render(
    <ul>
      <RunSteps tools={calls(tool("draw", "called"))} running />
    </ul>,
  );
  const words = screen.container.querySelector("button span.truncate") as HTMLElement;
  expect(words.getAnimations()).toHaveLength(forced ? 0 : 1);
});

test("unfurled on a desktop, its line controls the list, and a later failure says nothing again", async () => {
  const group = calls(tool("read_artifact"));
  const screen = await render(
    <ul>
      <RunSteps tools={group} running />
    </ul>,
  );
  await screen.rerender(
    <ul>
      <RunSteps tools={group} running={false} />
    </ul>,
  );
  const status = screen.getByRole("status");
  await expect.element(status).toHaveTextContent("Read an artifact");
  const failedNow = group.map(([id, each]) => [id, { ...each, status: "error" }] as const);
  await screen.rerender(
    <ul>
      <RunSteps tools={failedNow} running={false} />
    </ul>,
  );
  expect(status.element().textContent).toBe("Read an artifact");
  const line = screen.getByRole("button", { name: /: 1 tool call$/ });
  await line.click();
  expect(line.element().getAttribute("aria-controls")).toBe(
    screen.getByRole("list", { name: "Tool calls" }).element().id,
  );
  expect(line.element().hasAttribute("aria-haspopup")).toBe(false);
});
