import type { Artifactr } from "@portalr/client";
import { expect, onTestFinished, test, vi } from "vitest";
import { commands, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import { axeViolations } from "./test/axe";
import { RunSteps } from "./tool-call";
import { doneLabel, foldSummary } from "./tool-fold";

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

test("short of room, a line keeps whole kinds, the first two if they fit and else the first, and counts the rest", () => {
  const four = run(
    ["find_commands", 1],
    ["edit_native", 1],
    ["archive_artifact", 1],
    ["mystery", 2],
  );
  // All of it fits: all of it is said.
  expect(doneLabel(four, 80)).toBe(
    "Looked up commands, edited a file, archived an artifact, used 2 tools",
  );
  // Two kinds fit; the calls of the others are counted.
  expect(doneLabel(four, 45)).toBe("Looked up commands, edited a file and 3 more");
  // Only the first fits.
  expect(doneLabel(four, 30)).toBe("Looked up commands and 4 more");
  // Not even that: the first is kept whole all the same, never cut.
  expect(doneLabel(four, 5)).toBe("Looked up commands and 4 more");
  // Two kinds, both fit, or the one that does.
  const two = run(["create_artifact", 2], ["mystery", 3]);
  expect(doneLabel(two, 40)).toBe("Made 2 artifacts, used 3 tools");
  expect(doneLabel(two, 20)).toBe("Made 2 artifacts and 3 more");
  // One kind has nothing to count after it.
  expect(doneLabel(run(["draw", 30]), 3)).toBe("Drew 30 diagrams");
  // Two kinds, the first too long for the line, and a third behind them.
  expect(doneLabel(run(["comment_on_item", 1], ["mystery", 1], ["draw", 1]), 10)).toBe(
    "Commented on an item and 2 more",
  );
});

test("the line's words never end mid-phrase, however little room there is", () => {
  const many = run(["find_commands", 2], ["edit_native", 1], ["archive_artifact", 3], ["x", 4]);
  const kinds = doneLabel(many).split(", ");
  for (let room = 0; room < 90; room += 1) {
    // The first kinds of it, whole, then perhaps "and N more", and nothing else.
    const [kept = "", more] = doneLabel(many, room).split(/ and (\d+) more$/);
    const at = kept.split(", ").length;
    expect(kinds.slice(0, at).join(", ")).toBe(kept);
    expect(at === kinds.length || at <= 2).toBe(true);
    expect(more === undefined).toBe(at === kinds.length);
    expect(foldSummary(many, false, room).full).toBe(doneLabel(many));
  }
});

test("while a call runs the line says it is doing it; a failure is counted", () => {
  expect(foldSummary([tool("read_artifact"), tool("create_app", "called")])).toEqual({
    label: "Making an app…",
    full: "Making an app…",
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

test("a long line is cut to one, with the whole in its name", async () => {
  const many = ["create_app", "read_artifact", "draw", "fetch", "send_message", "post_notice"];
  const screen = await render(
    <div className="w-60">
      <ul>
        <RunSteps tools={calls(...many.map((name) => tool(name)))} />
      </ul>
    </div>,
  );
  const words = screen.container.querySelector("button span.truncate") as HTMLElement;
  expect(words.scrollWidth).toBeGreaterThan(words.clientWidth);
  await expect
    .element(screen.getByRole("button", { name: /posted a notice: 6 tool calls$/ }))
    .toBeVisible();
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
