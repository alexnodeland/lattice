import type { Artifactr } from "@portalr/client";
import { expect, onTestFinished, test, vi } from "vitest";
import { render } from "vitest-browser-react";
import { Messages, RunStrip, Streaming } from "./chat";
import { useRetrying } from "./on-demand";
import { ToolCall, ToolCalls } from "./tool-call";

// The strip and a call load their add-ons through `useRetrying`, keyed so that one that failed
// to load is tried again as a new run starts, or the call is opened again (`on-demand.test.ts`
// holds the hook to that).
vi.mock("./on-demand", async (original) => {
  const real = await original<typeof import("./on-demand")>();
  return { ...real, useRetrying: vi.fn(real.useRetrying) };
});

const live: Artifactr.Live = {
  phase: "writing",
  tool: null,
  calls: 0,
  argsChars: 0,
  thinking: "",
  thoughtMs: 0,
  outputChars: 0,
  since: 0,
  at: 0,
  part: null,
  reply: "writing",
  truncated: false,
  framed: false,
  usage: null,
};
const run = (id: string): Artifactr.Run =>
  ({
    id,
    threadId: "t",
    status: "running",
    tools: {},
    text: "",
    live,
    requests: [],
    answered: [],
    started: 1,
    startedAt: "2026-10-27T10:00:00Z",
    ended: null,
    error: null,
    reason: null,
    prompt: [],
    actsFor: null,
    questions: [],
    feedback: [],
  }) as Artifactr.Run;

const keys = () => vi.mocked(useRetrying).mock.calls.map(([, wanted, key]) => [wanted, key]);

test("the strip keys its add-on by the run, so a failed load is tried again as the next starts", async () => {
  const screen = await render(<RunStrip run={run("run_1")} now={new Date()} />);
  expect(keys().at(-1)).toEqual([true, "run_1"]);
  await screen.rerender(<RunStrip run={run("run_2")} now={new Date()} />);
  expect(keys().at(-1)).toEqual([true, "run_2"]);
});

test("a call keys its add-on by being open, so a failed load is tried again as it is opened again", async () => {
  const tool: Artifactr.Tool = {
    name: "a",
    status: "ok",
    args: "{}",
    result: "ok",
    argsCut: false,
    resultCut: false,
    seq: 1,
  };
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool} />
    </ToolCalls>,
  );
  expect(keys().at(-1)).toEqual([false, false]);
  await screen.getByText("a").click();
  expect(keys().at(-1)).toEqual([true, true]);
});

test("before the formatted view loads, a call's Copy copies what it shows", async () => {
  const retrying = vi.mocked(useRetrying);
  const real = retrying.getMockImplementation();
  retrying.mockImplementation(() => null);
  onTestFinished(() => {
    retrying.mockImplementation(real ?? (() => null));
  });
  const written = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  onTestFinished(() => written.mockRestore());
  const tool: Artifactr.Tool = {
    name: "create_artifact",
    status: "called",
    args: '{"kind": "note"}',
    result: "",
    argsCut: false,
    resultCut: false,
    seq: 1,
  };
  const screen = await render(
    <ToolCalls>
      <ToolCall tool={tool} open />
    </ToolCalls>,
  );
  const region = screen.getByRole("region", { name: "The arguments of create_artifact" });
  await expect.element(region).toBeVisible();
  await screen.getByRole("button", { name: "Copy the arguments of create_artifact" }).click();
  expect(written).toHaveBeenLastCalledWith(region.element().textContent);
});

test("before the streaming add-on loads, an ended turn's thinking says it thought", async () => {
  const retrying = vi.mocked(useRetrying);
  const real = retrying.getMockImplementation();
  retrying.mockImplementation(() => null);
  onTestFinished(() => {
    retrying.mockImplementation(real ?? (() => null));
  });
  const thinking = { ...live, phase: "thinking" as const, thinking: "mm" };
  const screen = await render(
    <Messages>
      <Streaming text="" live={thinking} ended="failed" author="Assistant" />
    </Messages>,
  );
  await expect.element(screen.getByRole("button", { name: "Thought", exact: true })).toBeVisible();
  await screen.rerender(
    <Messages>
      <Streaming text="" live={thinking} author="Assistant" />
    </Messages>,
  );
  await expect.element(screen.getByRole("button", { name: "Thinking…" })).toBeVisible();
});
