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
  expect(doneLabel([tool("search_web"), tool("mcp_thing"), tool("fetch")])).toBe(
    "Used 2 tools, fetched a page",
  );
});

test("while a call runs the line says it is doing it; a failure is counted", () => {
  expect(foldSummary([tool("read_artifact"), tool("create_app", "called")])).toEqual({
    label: "Making an app…",
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
      <RunSteps tools={first} />
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
      <RunSteps tools={more} />
    </ul>,
  );
  await expect
    .element(screen.getByRole("button", { name: "Drawing a diagram…: 3 tool calls" }))
    .toHaveAttribute("aria-expanded", "true");
  const done = more.map(([id, each]) => [id, { ...each, status: "ok" }] as const);
  await screen.rerender(
    <ul>
      <RunSteps tools={done} />
    </ul>,
  );
  expect(words().getAnimations()).toHaveLength(0);
  expect(words().style.color).toBe("");
  await expect
    .element(screen.getByRole("status"))
    .toHaveTextContent("Read an artifact, made an app, drew a diagram");
});

test("which groups were opened is kept as the thread is shown again", async () => {
  const same = calls(tool("fetch"));
  const first = await render(
    <ul>
      <RunSteps tools={same} />
    </ul>,
  );
  await first.getByRole("button", { name: "Fetched a page: 1 tool call" }).click();
  await first.unmount();
  const again = await render(
    <ul>
      <RunSteps tools={same} />
    </ul>,
  );
  await expect
    .element(again.getByRole("button", { name: "Fetched a page: 1 tool call" }))
    .toHaveAttribute("aria-expanded", "true");
});
