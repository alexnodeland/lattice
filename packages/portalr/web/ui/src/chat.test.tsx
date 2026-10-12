import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import {
  Composer,
  Message,
  Messages,
  ProposalCard,
  Request,
  RunStatus,
  Streaming,
  ToolCall,
} from "./chat";
import { token } from "./test/colours";

const alice = { kind: "user", id: "alice" } as ArtifactrV1.Actor;

function message(change: Partial<Artifactr.Message> = {}): Artifactr.Message {
  return {
    id: "msg_1",
    seq: 1,
    actor: alice,
    content: "The plan is **ready**.",
    kind: "message",
    runId: null,
    feedback: [],
    ...change,
  };
}

const thumbs = (up: boolean): Artifactr.Feedback => ({
  actor: alice,
  type: "thumbs",
  value: { up },
});

test("a message shows who posted it, and its Markdown", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="Alice" me="alice" />
    </Messages>,
  );
  const list = screen.getByRole("list", { name: "Messages" });
  await expect.element(list.getByText("Alice")).toBeVisible();
  await expect.element(list.getByText("ready")).toBeVisible();
});

test("thumbs show the reader's latest, and send theirs", async () => {
  const onThumbs = vi.fn();
  const screen = await render(
    <Messages>
      <Message
        message={message({ feedback: [thumbs(false), thumbs(true)] })}
        author="Agent"
        me="alice"
        onThumbs={onThumbs}
      />
    </Messages>,
  );
  const up = screen.getByRole("button", { name: "Helpful" });
  await expect.element(up).toHaveAttribute("aria-pressed", "true");
  await expect
    .element(screen.getByRole("button", { name: "Not helpful" }))
    .toHaveAttribute("aria-pressed", "false");
  await screen.getByRole("button", { name: "Not helpful" }).click();
  expect(onThumbs).toHaveBeenCalledWith(false);
});

test("someone else's thumbs aren't the reader's", async () => {
  const bob = { ...thumbs(true), actor: { kind: "user", id: "bob" } as ArtifactrV1.Actor };
  const screen = await render(
    <Messages>
      <Message
        message={message({ feedback: [bob] })}
        author="Agent"
        me="alice"
        onThumbs={vi.fn()}
      />
    </Messages>,
  );
  await expect
    .element(screen.getByRole("button", { name: "Helpful" }))
    .toHaveAttribute("aria-pressed", "false");
});

test("a notice is set apart from messages", async () => {
  const screen = await render(
    <Messages>
      <Message
        message={message({ kind: "notice", content: "Run stopped" })}
        author="System"
        me="alice"
      />
    </Messages>,
  );
  const notice = screen.getByRole("listitem").element();
  expect(getComputedStyle(notice).fontStyle).toBe("italic");
  expect(getComputedStyle(notice).color).toBe(token("muted"));
});

test("streaming text shows as it arrives, marked busy", async () => {
  const screen = await render(
    <Messages>
      <Streaming text="Working on **it" author="Agent" />
    </Messages>,
  );
  const writing = screen.getByRole("listitem", { name: "Agent is writing" });
  await expect.element(writing).toHaveAttribute("aria-busy", "true");
  await expect.element(writing.getByText("it")).toBeVisible();
});

test("the composer sends what is written, on Enter or with the button, and clears", async () => {
  const onSend = vi.fn();
  const screen = await render(<Composer onSend={onSend} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await expect.element(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  await box.fill("Draft the plan");
  await userEvent.keyboard("{Enter}");
  expect(onSend).toHaveBeenLastCalledWith("Draft the plan");
  await expect.element(box).toHaveValue("");
  await box.fill("Line one");
  await userEvent.keyboard("{Shift>}{Enter}{/Shift}");
  await expect.element(box).toHaveValue("Line one\n");
  await screen.getByRole("button", { name: "Send" }).click();
  expect(onSend).toHaveBeenLastCalledWith("Line one");
  expect(onSend).toHaveBeenCalledTimes(2);
});

test("a disabled composer sends nothing", async () => {
  const screen = await render(<Composer onSend={vi.fn()} disabled />);
  await expect.element(screen.getByRole("textbox", { name: "Message" })).toBeDisabled();
});

test("the composer reached by the keyboard shows the focus ring", async () => {
  const screen = await render(<Composer onSend={vi.fn()} />);
  await userEvent.tab();
  const box = screen.getByRole("textbox", { name: "Message" }).element();
  expect(box.matches(":focus-visible")).toBe(true);
  expect(getComputedStyle(box).outlineColor).toBe(token("focus"));
});

test("a tool call says it is running until it returns", async () => {
  const screen = await render(
    <ul>
      <ToolCall tool={{ name: "edit_artifact", status: "called" }} />
      <ToolCall tool={{ name: "read_artifact", status: "ok" }} />
    </ul>,
  );
  await expect.element(screen.getByText("running")).toBeVisible();
  await expect.element(screen.getByText("ok")).toBeVisible();
});

test("a call to approve is approved or denied", async () => {
  const onAnswer = vi.fn();
  const request = {
    kind: "approval",
    tool_call_id: "t1",
    tool_name: "archive_artifact",
    args: { artifact_id: "plan_1" },
  } as ArtifactrV1.DeferredRequest;
  const screen = await render(<Request request={request} onAnswer={onAnswer} />);
  const card = screen.getByRole("region", { name: "Approve archive_artifact?" });
  await expect.element(card.getByText(/"artifact_id": "plan_1"/)).toBeVisible();
  await card.getByRole("button", { name: "Approve" }).click();
  await card.getByRole("button", { name: "Deny" }).click();
  expect(onAnswer.mock.calls).toEqual([[{ approved: true }], [{ approved: false }]]);
});

test("a question is answered", async () => {
  const onAnswer = vi.fn();
  const request = {
    kind: "question",
    tool_call_id: "t2",
    tool_name: "ask_user",
    args: { question: "Which week?" },
  } as ArtifactrV1.DeferredRequest;
  const screen = await render(<Request request={request} onAnswer={onAnswer} />);
  await expect.element(screen.getByText("Which week?")).toBeVisible();
  await screen.getByRole("textbox", { name: "Answer" }).fill("The next");
  await screen.getByRole("button", { name: "Answer" }).click();
  expect(onAnswer).toHaveBeenCalledWith({ answer: "The next" });
});

const proposal = (change: Partial<Artifactr.Proposal> = {}): Artifactr.Proposal => ({
  id: "prop_1",
  threadId: "thr_1",
  runId: "run_1",
  change: {
    type: "edit_artifact",
    artifact_id: "plan_1",
    base_version: 1,
    patch: { kind: "text_edits", edits: [] },
    summary: "Tighten the launch plan",
  } as unknown as Artifactr.Proposal["change"],
  rationale: "It was long.",
  status: "open",
  ...change,
});

test("an open proposal says what it would change, and is accepted or rejected", async () => {
  const onRespond = vi.fn();
  const screen = await render(<ProposalCard proposal={proposal()} onRespond={onRespond} />);
  const card = screen.getByRole("region", { name: "Proposal: Tighten the launch plan" });
  await expect.element(card.getByText("It was long.")).toBeVisible();
  await card.getByRole("button", { name: "Accept" }).click();
  await card.getByRole("button", { name: "Reject" }).click();
  expect(onRespond.mock.calls).toEqual([["accept"], ["reject"]]);
});

test("a resolved proposal says how, without buttons", async () => {
  const screen = await render(
    <>
      <ProposalCard proposal={proposal({ status: "accept" })} onRespond={vi.fn()} />
      <ProposalCard
        proposal={proposal({ id: "prop_2", status: "reject", change: null, rationale: null })}
      />
    </>,
  );
  await expect.element(screen.getByText("Accepted")).toBeVisible();
  await expect.element(screen.getByRole("region", { name: "Proposal: A change" })).toBeVisible();
  await expect.element(screen.getByText("Rejected")).toBeVisible();
  expect(screen.getByRole("button").elements()).toHaveLength(0);
});

test("a proposal to create or archive names the artifact", async () => {
  const create = {
    type: "create_artifact",
    kind: "plan",
    data: {},
  } as Artifactr.Proposal["change"];
  const archive = {
    type: "archive_artifact",
    artifact_id: "plan_1",
    base_version: 2,
  } as Artifactr.Proposal["change"];
  const screen = await render(
    <>
      <ProposalCard proposal={proposal({ change: create })} />
      <ProposalCard proposal={proposal({ id: "prop_3", change: archive })} />
    </>,
  );
  await expect.element(screen.getByText("Create a plan")).toBeVisible();
  await expect.element(screen.getByText("Archive plan_1")).toBeVisible();
});

test("a run's status is announced in words", async () => {
  const screen = await render(
    <>
      <RunStatus status="paused" />
      <RunStatus status="interrupted" />
    </>,
  );
  const [paused, other] = screen.getByRole("status").elements();
  expect(paused?.textContent).toBe("Waiting for you");
  expect(other?.textContent).toBe("interrupted");
});

test("the message list takes a caller's classes", async () => {
  const screen = await render(<Messages className="gap-8">{null}</Messages>);
  const list = screen.getByRole("list", { name: "Messages" }).element();
  expect(list.classList).toContain("gap-8");
  expect(list.classList).not.toContain("gap-4");
});
