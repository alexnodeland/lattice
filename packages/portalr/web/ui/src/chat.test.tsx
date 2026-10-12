import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import { expect, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import {
  Composer,
  Message,
  Messages,
  ProposalCard,
  proposedOn,
  Request,
  RunStatus,
  Streaming,
  ToolCall,
} from "./chat";
import { contrast, token } from "./test/colours";

/** A command handler whose commands end as `outcome`. */
const sent = (outcome: "done" | "refused" | "closed" = "done") => vi.fn(async () => ({ outcome }));

function message(change: Partial<Artifactr.Message> = {}): Artifactr.Message {
  return {
    id: "msg_1",
    seq: 1,
    actor: { kind: "user", id: "alice" },
    content: "The plan is **ready**.",
    kind: "message",
    runId: null,
    feedback: [],
    ...change,
  };
}

test("a message shows who posted it, and its Markdown, in the thread's log", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="Alice" />
    </Messages>,
  );
  const log = screen.getByRole("log", { name: "Messages" });
  await expect.element(log.getByText("Alice")).toBeVisible();
  await expect.element(log.getByText("ready")).toBeVisible();
});

test("thumbs show the reader's, and send theirs", async () => {
  const onThumbs = sent();
  const screen = await render(
    <Messages>
      <Message message={message()} author="Agent" thumbs={true} onThumbs={onThumbs} />
    </Messages>,
  );
  const up = screen.getByRole("button", { name: "Helpful", exact: true });
  const down = screen.getByRole("button", { name: "Not helpful" });
  await expect.element(up).toHaveAttribute("aria-pressed", "true");
  await expect.element(down).toHaveAttribute("aria-pressed", "false");
  await down.click();
  expect(onThumbs).toHaveBeenCalledWith(false);
});

test("without thumbs given, neither is pressed; without a handler, there are none", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="Agent" onThumbs={sent()} />
      <Message message={message({ id: "msg_2" })} author="Alice" />
    </Messages>,
  );
  const buttons = screen.getByRole("button").elements();
  expect(buttons).toHaveLength(2);
  for (const button of buttons) {
    expect(button.getAttribute("aria-pressed")).toBe("false");
  }
});

test("a notice is set apart from messages", async () => {
  const screen = await render(
    <Messages>
      <Message message={message({ kind: "notice", content: "Run stopped" })} author="System" />
    </Messages>,
  );
  const notice = screen.getByRole("listitem", { name: "System" }).element();
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
  const onSend = sent();
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

test("Enter while an input method composes doesn't send", async () => {
  const onSend = sent();
  const screen = await render(<Composer onSend={onSend} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("日本");
  const composing = new KeyboardEvent("keydown", {
    key: "Enter",
    isComposing: true,
    bubbles: true,
  });
  box.element().dispatchEvent(composing);
  expect(onSend).not.toHaveBeenCalled();
  await expect.element(box).toHaveValue("日本");
});

test("a disabled composer sends nothing, and looks it", async () => {
  const screen = await render(<Composer onSend={sent()} disabled />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await expect.element(box).toBeDisabled();
  const style = getComputedStyle(box.element());
  expect(style.opacity).toBe("1");
  expect(style.color).toBe(token("muted"));
  expect(contrast(style.color, style.backgroundColor)).toBeGreaterThanOrEqual(4.5);
});

test("the composer reached by the keyboard shows the focus ring", async () => {
  const screen = await render(<Composer onSend={sent()} />);
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

test("a call to approve takes the focus, and is approved or denied once", async () => {
  const onAnswer = sent();
  const request: ArtifactrV1.DeferredRequest = {
    kind: "approval",
    tool_call_id: "t1",
    tool_name: "archive_artifact",
    args: { artifact_id: "plan_1" },
  };
  const screen = await render(<Request request={request} onAnswer={onAnswer} />);
  const card = screen.getByRole("region", { name: "Approve archive_artifact?" });
  await expect.element(card.getByText(/"artifact_id": "plan_1"/)).toBeVisible();
  const approve = card.getByRole("button", { name: "Approve" });
  await expect.element(approve).toHaveFocus();
  await approve.click();
  await expect.element(approve).toBeDisabled();
  await expect.element(card.getByRole("button", { name: "Deny" })).toBeDisabled();
  expect(onAnswer.mock.calls).toEqual([[{ approved: true }]]);
});

test("a call can be denied", async () => {
  const onAnswer = sent();
  const request: ArtifactrV1.DeferredRequest = {
    kind: "approval",
    tool_call_id: "t1",
    tool_name: "publish",
  };
  const screen = await render(<Request request={request} onAnswer={onAnswer} />);
  await screen.getByRole("button", { name: "Deny" }).click();
  expect(onAnswer).toHaveBeenCalledWith({ approved: false });
});

test("a question takes the focus, and is answered once", async () => {
  const onAnswer = sent();
  const request: ArtifactrV1.DeferredRequest = {
    kind: "question",
    tool_call_id: "t2",
    tool_name: "ask_user",
    args: { question: "Which week?" },
  };
  const screen = await render(<Request request={request} onAnswer={onAnswer} />);
  await expect.element(screen.getByText("Which week?")).toBeVisible();
  const field = screen.getByRole("textbox", { name: "Answer" });
  await expect.element(field).toHaveFocus();
  await field.fill("The next");
  await screen.getByRole("button", { name: "Answer" }).click();
  expect(onAnswer).toHaveBeenCalledWith({ answer: "The next" });
  await expect.element(screen.getByRole("button", { name: "Answer" })).toBeDisabled();
});

test("a question without its words names the tool that asks", async () => {
  const request: ArtifactrV1.DeferredRequest = {
    kind: "question",
    tool_call_id: "t3",
    tool_name: "confirm",
  };
  const screen = await render(<Request request={request} onAnswer={sent()} />);
  await expect.element(screen.getByText("The agent asks, through confirm.")).toBeVisible();
});

const edit: Artifactr.Proposal["change"] = {
  type: "edit_artifact",
  artifact_id: "plan_1",
  base_version: 1,
  patch: { kind: "text_edits", edits: [{ old: "a long plan", new: "a plan" }] },
  summary: "Tighten the launch plan",
};

const proposal = (change: Partial<Artifactr.Proposal> = {}): Artifactr.Proposal => ({
  id: "prop_1",
  threadId: "thr_1",
  runId: "run_1",
  change: edit,
  rationale: "It was long.",
  status: "open",
  ...change,
});

test("an open proposal says what it would change, and is accepted or rejected", async () => {
  const onRespond = sent();
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
      <ProposalCard proposal={proposal({ status: "accept" })} onRespond={sent()} />
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

test("a proposal to create, edit without a summary, or archive names the artifact", async () => {
  const create: Artifactr.Proposal["change"] = { type: "create_artifact", kind: "plan", data: {} };
  const unsummed: Artifactr.Proposal["change"] = {
    type: "edit_artifact",
    artifact_id: "plan_1",
    base_version: 1,
    patch: { kind: "text_edits", edits: [{ old: "a", new: "b" }] },
  };
  const archive: Artifactr.Proposal["change"] = {
    type: "archive_artifact",
    artifact_id: "plan_1",
    base_version: 2,
  };
  const screen = await render(
    <>
      <ProposalCard proposal={proposal({ change: create })} />
      <ProposalCard proposal={proposal({ id: "prop_2", change: unsummed })} />
      <ProposalCard proposal={proposal({ id: "prop_3", change: archive })} />
    </>,
  );
  await expect.element(screen.getByText("Create a plan")).toBeVisible();
  await expect.element(screen.getByText("Edit plan_1")).toBeVisible();
  await expect.element(screen.getByText("Archive plan_1")).toBeVisible();
});

test("a run's status is announced in words", async () => {
  const screen = await render(
    <>
      <RunStatus status="paused" />
      <RunStatus status="completed" />
    </>,
  );
  const [paused, done] = screen.getByRole("status").elements();
  expect(paused?.textContent).toBe("Waiting for you");
  expect(done?.textContent).toBe("Done");
});

test("the message list takes a caller's classes", async () => {
  const screen = await render(<Messages className="gap-8">{null}</Messages>);
  const list = screen.getByRole("list").element();
  expect(list.classList).toContain("gap-8");
  expect(list.classList).not.toContain("gap-4");
});

test("a message is named for who posted it", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="Alice" />
      <Message message={message({ id: "msg_2" })} author="Assistant" />
    </Messages>,
  );
  await expect.element(screen.getByRole("listitem", { name: "Assistant" })).toBeVisible();
  await expect.element(screen.getByRole("listitem", { name: "Alice" })).toBeVisible();
});

test("a refused post keeps its text, and says it wasn't done", async () => {
  const screen = await render(<Composer onSend={sent("refused")} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("Draft the plan");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("That wasn't done: the server refused it.");
  await expect.element(box).toHaveValue("Draft the plan");
});

test("a post waits for its answer before another can be sent", async () => {
  let done: (value: { outcome: "done" }) => void = () => undefined;
  const onSend = vi.fn(() => new Promise<{ outcome: "done" }>((resolve) => (done = resolve)));
  const screen = await render(<Composer onSend={onSend} />);
  await screen.getByRole("textbox", { name: "Message" }).fill("One");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  await userEvent.keyboard("{Enter}");
  expect(onSend).toHaveBeenCalledOnce();
  done({ outcome: "done" });
  await expect.element(screen.getByRole("textbox", { name: "Message" })).toHaveValue("");
});

test("an answer that wasn't sent can be given again", async () => {
  const onAnswer = sent("closed");
  const request: ArtifactrV1.DeferredRequest = {
    kind: "approval",
    tool_call_id: "t1",
    tool_name: "publish",
  };
  const screen = await render(<Request request={request} onAnswer={onAnswer} />);
  await screen.getByRole("button", { name: "Approve" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("That wasn't sent: the connection closed.");
  await expect.element(screen.getByRole("button", { name: "Approve" })).toBeEnabled();
});

test("a refused response to a proposal says so, and can be given again", async () => {
  const screen = await render(<ProposalCard proposal={proposal()} onRespond={sent("refused")} />);
  await screen.getByRole("button", { name: "Accept" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("That wasn't done: the server refused it.");
  await expect.element(screen.getByRole("button", { name: "Accept" })).toBeEnabled();
});

test("refused thumbs say so", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="Agent" onThumbs={sent("refused")} />
    </Messages>,
  );
  await screen.getByRole("button", { name: "Helpful", exact: true }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("That wasn't done: the server refused it.");
});

test("a proposal holds what its caller adds", async () => {
  const screen = await render(
    <ProposalCard proposal={proposal()}>
      <a href="#plan_1">plan_1</a>
    </ProposalCard>,
  );
  const card = screen.getByRole("region", { name: "Proposal: Tighten the launch plan" });
  await expect.element(card.getByRole("link", { name: "plan_1" })).toBeVisible();
});

test("a proposal names the artifact it would change, unless it makes a new one", () => {
  expect(proposedOn(proposal())).toBe("plan_1");
  expect(
    proposedOn(proposal({ change: { type: "create_artifact", kind: "plan", data: {} } })),
  ).toBeNull();
  expect(proposedOn(proposal({ change: null }))).toBeNull();
});
