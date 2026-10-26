import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import { describe, expect, onTestFinished, test, vi } from "vitest";
import { userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import {
  ActionsMenu,
  CommandButton,
  Composer,
  Message,
  Messages,
  ProposalCard,
  proposedOn,
  Request,
  RunStatus,
  Streaming,
  Thumbs,
  unhidden,
} from "./chat";
import { IntegrationsContext } from "./integrations";
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
      <Message
        message={message()}
        author="Agent"
        thumbs={{ up: true, comment: null }}
        onThumbs={onThumbs}
      />
    </Messages>,
  );
  const up = screen.getByRole("button", { name: "Helpful", exact: true });
  const down = screen.getByRole("button", { name: "Not helpful" });
  await expect.element(up).toHaveAttribute("aria-pressed", "true");
  await expect.element(down).toHaveAttribute("aria-pressed", "false");
  await down.click();
  expect(onThumbs).toHaveBeenCalledWith(false, null);
});

test("without thumbs given, neither is pressed; without a handler, there are none", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="Agent" onThumbs={sent()} />
      <Message message={message({ id: "msg_2" })} author="Alice" />
    </Messages>,
  );
  const thumbs = screen.getByRole("group", { name: "Feedback" }).getByRole("button").elements();
  expect(thumbs).toHaveLength(2);
  expect(screen.getByRole("group", { name: "Feedback" }).elements()).toHaveLength(1);
  for (const button of thumbs) {
    expect(button.getAttribute("aria-pressed")).toBe("false");
  }
});

test("each message can be copied as the Markdown it was written in, never as what shows", async () => {
  const written = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  onTestFinished(() => written.mockRestore());
  const content = "# Plan\n\n- **one**\n\n```ts\nlet x = 1;\n```";
  const screen = await render(
    <Messages>
      <Message message={message({ content })} author="Agent" />
    </Messages>,
  );
  await screen.getByRole("button", { name: "Copy as Markdown" }).click();
  expect(written).toHaveBeenCalledWith(content);
  await expect.element(screen.getByRole("button", { name: "Copied as Markdown" })).toBeVisible();
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

test("the reader's messages are at the end of the line, everyone else's at its start", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="You" mine />
      <Message message={message({ id: "msg_2" })} author="Assistant" />
    </Messages>,
  );
  const mine = screen.getByRole("listitem", { name: "You" }).element();
  const theirs = screen.getByRole("listitem", { name: "Assistant" }).element();
  expect(getComputedStyle(mine).alignSelf).toBe("flex-end");
  expect(getComputedStyle(theirs).alignSelf).toBe("flex-start");
  const list = mine.parentElement as HTMLElement;
  const [start, end] = [list.getBoundingClientRect(), mine.getBoundingClientRect()];
  expect(Math.round(end.right)).toBe(Math.round(start.right));
  // Right to left, the reader's go to the left: the line's end.
  list.dir = "rtl";
  expect(Math.round(mine.getBoundingClientRect().left)).toBe(Math.round(start.left));
});

test("a message on its way says so, and can't be copied or judged yet", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="You" mine sending onThumbs={sent()} />
    </Messages>,
  );
  const posting = screen.getByRole("listitem", { name: "You" });
  await expect.element(posting).toHaveAttribute("aria-busy", "true");
  await expect.element(posting.getByText("Sending…")).toBeVisible();
  expect(posting.getByRole("button").elements()).toHaveLength(0);
});

test("before its first words, a run says the agent is thinking, and stays still if asked", async () => {
  const screen = await render(
    <Messages>
      <Streaming text="" author="Assistant" />
    </Messages>,
  );
  const thinking = screen.getByRole("listitem", { name: "Assistant is thinking" });
  await expect.element(thinking).toHaveAttribute("aria-busy", "true");
  await expect.element(thinking.getByText("Thinking")).toBeInTheDocument();
  const dot = thinking.element().querySelector(".rounded-full") as Element;
  expect(getComputedStyle(dot).animationName).toBe("none"); // the tests reduce motion
});

test("what streams sits where its message will, so nothing moves when it is posted", async () => {
  const screen = await render(
    <Messages>
      <Streaming text="Done." author="Assistant" />
    </Messages>,
  );
  const streaming = screen.getByRole("listitem", { name: "Assistant is writing" }).element();
  const before = streaming.getBoundingClientRect();
  await screen.rerender(
    <Messages>
      <Message message={message({ content: "Done." })} author="Assistant" />
    </Messages>,
  );
  const posted = screen.getByRole("listitem", { name: "Assistant" }).element();
  const after = posted.getBoundingClientRect();
  expect([after.top, after.left, after.height]).toEqual([before.top, before.left, before.height]);
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

test("a draft not yet sent asks before the page is left or reloaded", async () => {
  const screen = await render(<Composer onSend={sent()} />);
  const leave = () => {
    const event = new Event("beforeunload", { cancelable: true });
    dispatchEvent(event);
    return event.defaultPrevented;
  };
  expect(leave()).toBe(false);
  await screen.getByRole("textbox", { name: "Message" }).fill("Half a thought");
  await vi.waitFor(() => expect(leave()).toBe(true));
  await screen.getByRole("textbox", { name: "Message" }).fill("");
  await vi.waitFor(() => expect(leave()).toBe(false));
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
  expect(contrast(style.color, token("surface"))).toBeGreaterThanOrEqual(4.5);
});

test("the composer reached by the keyboard rings the whole of it in the focus colour", async () => {
  const screen = await render(<Composer onSend={sent()} />);
  await userEvent.tab();
  const box = screen.getByRole("textbox", { name: "Message" }).element();
  expect(box).toBe(document.activeElement);
  const composer = getComputedStyle(box.closest("form") as Element);
  expect(composer.outlineStyle).toBe("solid");
  expect(composer.outlineColor).toBe(token("focus"));
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

test("a connected app's code is shown whole, with what it runs as and what a scan found", async () => {
  const onAnswer = sent();
  const code = "import os\nos.listdir('.')\n";
  const request: ArtifactrV1.DeferredRequest = {
    kind: "approval",
    tool_call_id: "t1",
    tool_name: "freecad_execute_code",
    args: { code },
    review: {
      app: "FreeCAD",
      risk: "code",
      runs: "Runs code in your FreeCAD, in the session you have open, with your own privileges.",
      code,
      findings: ["line 1: imports os"],
    },
  };
  const screen = await render(<Request request={request} onAnswer={onAnswer} />);
  const card = screen.getByRole("region", { name: "Approve freecad_execute_code?" });
  await expect.element(card.getByText("Runs code in your FreeCAD", { exact: true })).toBeVisible();
  await expect.element(card.getByText(/with your own privileges/)).toBeVisible();
  await expect.element(card.getByRole("button", { name: "Copy the code" })).toBeVisible();
  await expect.element(card.getByText("line 1: imports os")).toBeVisible();
});

test("a scan that found nothing says it can't find everything, and long code says so", async () => {
  const code = Array.from({ length: 50 }, (_, n) => `x${n} = ${n}`).join("\n");
  const request: ArtifactrV1.DeferredRequest = {
    kind: "approval",
    tool_call_id: "t1",
    tool_name: "blender_execute_blender_code",
    args: { code },
    review: {
      app: "Blender",
      risk: "code",
      runs: "Runs code.",
      holds: "An approval holds.",
      code,
      findings: [],
    },
  };
  const screen = await render(<Request request={request} onAnswer={sent()} />);
  await expect
    .element(screen.getByText("A quick scan found nothing; it can't find everything."))
    .toBeVisible();
  await expect.element(screen.getByText(/It is 50 lines long/)).toBeVisible();
  await expect.element(screen.getByText("An approval holds.")).toBeVisible();
});

test("a download says where it reaches, and a call how many of the hour's it is", async () => {
  const request: ArtifactrV1.DeferredRequest = {
    kind: "approval",
    tool_call_id: "t1",
    tool_name: "blender_import_asset",
    args: { source: "sketchfab", id: "abc" },
    review: {
      app: "Blender",
      risk: "network",
      runs: "Downloads from the internet into your Blender.",
      reaches: "Sketchfab: api.sketchfab.com",
      holds: "An approval holds.",
      hour: "2 of the 30 calls to Blender this workspace may run an hour have run.",
    },
  };
  const screen = await render(<Request request={request} onAnswer={sent()} />);
  const card = screen.getByRole("region", { name: "Approve blender_import_asset?" });
  await expect.element(card.getByText("It reaches Sketchfab: api.sketchfab.com.")).toBeVisible();
  await expect
    .element(
      card.getByText("2 of the 30 calls to Blender this workspace may run an hour have run."),
    )
    .toBeVisible();
});

test("a character a reader wouldn't see is shown as its code point", () => {
  expect(unhidden("a\u202eb\u200bc\u0000")).toBe(
    "a\u27e6U+202E\u27e7b\u27e6U+200B\u27e7c\u27e6U+0000\u27e7",
  );
  expect(unhidden("plain\tcode\n")).toBe("plain\tcode\n");
  expect(unhidden("\u061c\u2028\u00ad\u{e0041}\ufe0f")).toBe(
    "\u27e6U+061C\u27e7\u27e6U+2028\u27e7\u27e6U+00AD\u27e7\u27e6U+E0041\u27e7\u27e6U+FE0F\u27e7",
  );
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

test("another tool's question takes the focus, and is answered once, in a line", async () => {
  const onAnswer = sent();
  const request: ArtifactrV1.DeferredRequest = {
    kind: "question",
    tool_call_id: "t2",
    tool_name: "ask_week",
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

test("a proposal that can't be accepted says why, keeps Accept in reach, and is rejected", async () => {
  const onRespond = sent();
  const screen = await render(
    <ProposalCard proposal={proposal()} onRespond={onRespond} blocked="Outdated: reject it." />,
  );
  const accept = screen.getByRole("button", { name: "Accept" });
  await expect.element(accept).toBeDisabled();
  await expect.element(accept).toHaveAccessibleDescription("Outdated: reject it.");
  await userEvent.tab();
  await expect.element(accept).toHaveFocus();
  await screen.getByRole("button", { name: "Reject" }).click();
  expect(onRespond.mock.calls).toEqual([["reject"]]);
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

test("a refused post gives its text back, and says it wasn't done", async () => {
  const screen = await render(<Composer onSend={sent("refused")} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("Draft the plan");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("That wasn't done: the server refused it.");
  await expect.element(box).toHaveValue("Draft the plan");
});

test("a post clears as it is sent, and waits for its answer before another can be sent", async () => {
  let done: (value: { outcome: "done" }) => void = () => undefined;
  const onSend = vi.fn(() => new Promise<{ outcome: "done" }>((resolve) => (done = resolve)));
  const screen = await render(<Composer onSend={onSend} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("One");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(box).toHaveValue("");
  await box.fill("Two");
  await expect.element(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  await userEvent.keyboard("{Enter}");
  expect(onSend).toHaveBeenCalledOnce();
  done({ outcome: "done" });
  await expect.element(screen.getByRole("button", { name: "Send" })).toBeEnabled();
  await expect.element(box).toHaveValue("Two");
});

test("a post refused comes back, unless something new was written", async () => {
  let done: (value: { outcome: "refused" }) => void = () => undefined;
  const onSend = vi.fn(() => new Promise<{ outcome: "refused" }>((resolve) => (done = resolve)));
  const screen = await render(<Composer onSend={onSend} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("One");
  await userEvent.keyboard("{Enter}");
  await box.fill("Two");
  done({ outcome: "refused" });
  await expect.element(screen.getByRole("alert")).toBeVisible();
  await expect.element(box).toHaveValue("Two");
});

test("a post whose answer never came stays with the thread, not back in the box", async () => {
  const screen = await render(<Composer onSend={sent("closed")} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("One");
  await userEvent.keyboard("{Enter}");
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("That wasn't sent: the connection closed.");
  await expect.element(box).toHaveValue("");
});

test("a message whose answer never came may not have been sent, and is sent again", async () => {
  const again = sent();
  const screen = await render(
    <Messages>
      <Message message={message()} author="You" mine sending onSendAgain={again} />
    </Messages>,
  );
  await expect.element(screen.getByText("It may not have been sent.")).toBeVisible();
  await screen.getByRole("button", { name: "Send again" }).click();
  expect(again).toHaveBeenCalledOnce();
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

test("a command refused as an integration off here says it isn't available", async () => {
  const off = vi.fn(async () => ({
    outcome: "refused" as const,
    result: { rejection: { type: "not_enabled", integration: "excalidraw" } },
  }));
  const screen = await render(<ProposalCard proposal={proposal()} onRespond={off} />);
  await screen.getByRole("button", { name: "Accept" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Not available in this workspace.");
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

test("thumbs, then why: each is sent as it is given", async () => {
  const onThumbs = sent();
  const screen = await render(<Thumbs given={null} onThumbs={onThumbs} />);
  const feedback = screen.getByRole("group", { name: "Feedback" });
  await feedback.getByRole("button", { name: "Not helpful" }).click();
  expect(onThumbs).toHaveBeenLastCalledWith(false, null);
  await feedback.getByRole("textbox", { name: "Why? (optional)" }).fill("It missed the date");
  await feedback.getByRole("button", { name: "Add" }).click();
  expect(onThumbs).toHaveBeenLastCalledWith(false, "It missed the date");
  await expect.element(feedback.getByRole("button", { name: "Add" })).not.toBeInTheDocument();
});

test("a comment left blank adds none", async () => {
  const onThumbs = sent();
  const screen = await render(<Thumbs given={null} onThumbs={onThumbs} />);
  await screen.getByRole("button", { name: "Helpful", exact: true }).click();
  await screen.getByRole("button", { name: "Add" }).click();
  expect(onThumbs).toHaveBeenLastCalledWith(true, null);
});

test("the reader's comment shows with their thumbs", async () => {
  const screen = await render(
    <Thumbs given={{ up: false, comment: "It missed the date" }} onThumbs={sent()} />,
  );
  await expect.element(screen.getByText("You said: It missed the date")).toBeVisible();
  await expect
    .element(screen.getByRole("button", { name: "Not helpful" }))
    .toHaveAttribute("aria-pressed", "true");
});

test("thumbs that weren't sent ask for no comment", async () => {
  const screen = await render(<Thumbs given={null} onThumbs={sent("refused")} />);
  await screen.getByRole("button", { name: "Helpful", exact: true }).click();
  await expect.element(screen.getByRole("alert")).toBeVisible();
  await expect.element(screen.getByRole("textbox")).not.toBeInTheDocument();
});

test("a command button waits for its command, and says why one wasn't done", async () => {
  const onSend = sent("refused");
  const screen = await render(<CommandButton onSend={onSend}>Retry</CommandButton>);
  await screen.getByRole("button", { name: "Retry" }).click();
  expect(onSend).toHaveBeenCalledOnce();
  await expect.element(screen.getByRole("alert")).toBeVisible();
  await expect.element(screen.getByRole("button", { name: "Retry" })).toBeEnabled();
});

describe("a form the agent asks", () => {
  const asked: ArtifactrV1.DeferredRequest = {
    kind: "question",
    tool_call_id: "t1",
    tool_name: "ask_form",
    args: {
      title: "Ship it?",
      schema: {
        type: "object",
        properties: { when: { type: "string", title: "When" } },
        required: ["when"],
      },
    },
  };

  test("is its fields, said to be the agent's, and takes the focus as it appears", async () => {
    const screen = await render(<Request request={asked} onAnswer={sent()} />);
    await expect.element(screen.getByText("The agent asks")).toBeVisible();
    await expect.element(screen.getByRole("form", { name: "Ship it?" })).toBeVisible();
    await expect.element(screen.getByRole("textbox", { name: "When (required)" })).toHaveFocus();
  });

  test("is answered once, with its values", async () => {
    const onAnswer = sent();
    const screen = await render(<Request request={asked} onAnswer={onAnswer} />);
    await screen.getByRole("textbox", { name: /When/ }).fill("Friday");
    await screen.getByRole("button", { name: "Ship it?" }).click();
    expect(onAnswer.mock.calls).toEqual([[{ answer: { when: "Friday" } }]]);
    await expect.element(screen.getByRole("status")).toHaveTextContent("Sent.");
  });

  test("answered, it says by whom in place of its fields", async () => {
    const screen = await render(<Request request={asked} onAnswer={sent()} answeredBy="Alice" />);
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("Answered: Alice answered it.");
    await expect.element(screen.getByRole("textbox")).not.toBeInTheDocument();
    await screen.rerender(<Request request={asked} onAnswer={sent()} answeredBy={null} />);
    await expect.element(screen.getByRole("status")).toHaveTextContent("Answered.");
  });

  test("answered by another first, it says so, and who, once it is known", async () => {
    const onAnswer = vi.fn(async () => ({
      outcome: "refused" as const,
      result: { rejection: { type: "invalid_state", message: "already answered" } },
    }));
    const screen = await render(<Request request={asked} onAnswer={onAnswer} />);
    await screen.getByRole("textbox", { name: /When/ }).fill("Friday");
    await screen.getByRole("button", { name: "Ship it?" }).click();
    await expect.element(screen.getByRole("status")).toHaveTextContent("Already answered.");
    await screen.rerender(<Request request={asked} onAnswer={onAnswer} answeredBy="Bob" />);
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("Already answered: Bob answered it first.");
  });

  test("refused as off, it says forms are off and keeps the answers, unsendable", async () => {
    const onAnswer = vi.fn(async () => ({
      outcome: "refused" as const,
      result: {
        rejection: {
          type: "not_enabled",
          message: "ui:forms is not available in this workspace",
          integration: "ui:forms",
        },
      },
    }));
    const screen = await render(<Request request={asked} onAnswer={onAnswer} />);
    await screen.getByRole("textbox", { name: /When/ }).fill("Friday");
    await screen.getByRole("button", { name: "Ship it?" }).click();
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("Not available in this workspace: forms are off. This can't be sent.");
    const when = screen.getByRole("textbox", { name: /When/ });
    await expect.element(when).toHaveValue("Friday");
    await expect.element(when).toBeDisabled();
    await expect.element(screen.getByRole("button", { name: "Ship it?" })).not.toBeInTheDocument();
  });

  test("with forms off in the workspace, it shows its fields, unsendable, and says so", async () => {
    const screen = await render(
      <IntegrationsContext value={(key) => key !== "ui:forms"}>
        <Request request={asked} onAnswer={sent()} />
      </IntegrationsContext>,
    );
    await expect
      .element(screen.getByRole("status"))
      .toHaveTextContent("Not available in this workspace: forms are off. This can't be sent.");
    await expect.element(screen.getByRole("textbox", { name: /When/ })).toBeDisabled();
    await expect.element(screen.getByRole("button", { name: "Ship it?" })).not.toBeInTheDocument();
  });

  test("refused for its values, it says why under the field", async () => {
    const onAnswer = vi.fn(async () => ({
      outcome: "refused" as const,
      result: {
        rejection: { type: "validation_failed", errors: [{ loc: ["when"], msg: "too early" }] },
      },
    }));
    const screen = await render(<Request request={asked} onAnswer={onAnswer} />);
    await screen.getByRole("textbox", { name: /When/ }).fill("Now");
    await screen.getByRole("button", { name: "Ship it?" }).click();
    await expect
      .element(screen.getByRole("textbox", { name: /When/ }))
      .toHaveAccessibleDescription("This isn't valid.");
  });

  test("without a title it has no heading, and its button says Send; a form it can't show says so", async () => {
    const untitled = await render(
      <Request request={{ ...asked, args: { schema: { type: "object" } } }} onAnswer={sent()} />,
    );
    await expect.element(untitled.getByRole("heading")).not.toBeInTheDocument();
    await expect.element(untitled.getByRole("form", { name: "Send" })).toBeVisible();
    await expect.element(untitled.getByRole("button", { name: "Send" })).toBeVisible();
    await untitled.rerender(
      <Request request={{ ...asked, args: { schema: { type: "tree" } } }} onAnswer={sent()} />,
    );
    await expect
      .element(untitled.getByRole("status"))
      .toHaveTextContent("This form can't be shown here: its fields aren't ones portalr can show.");
  });

  test("told another takes the focus, or answered, it doesn't take it", async () => {
    const screen = await render(<Request request={asked} onAnswer={sent()} focus={false} />);
    await expect.element(screen.getByRole("textbox", { name: /When/ })).not.toHaveFocus();
    const question: ArtifactrV1.DeferredRequest = {
      kind: "question",
      tool_call_id: "t2",
      tool_name: "ask_week",
      args: { question: "Which?" },
    };
    await screen.rerender(<Request request={question} onAnswer={sent()} focus={false} />);
    await expect.element(screen.getByRole("textbox", { name: "Answer" })).not.toHaveFocus();
  });

  test("open, it carries a rule in the working colour at its start; answered, it doesn't", async () => {
    const screen = await render(<Request request={asked} onAnswer={sent()} />);
    const card = screen.getByText("The agent asks").element().parentElement as Element;
    expect(getComputedStyle(card).borderLeftColor).toBe(token("accent"));
    expect(getComputedStyle(card).borderLeftWidth).toBe("4px");
    expect(getComputedStyle(card).borderTopColor).toBe(token("line"));
    await screen.rerender(<Request request={asked} onAnswer={sent()} answeredBy="Alice" />);
    expect(getComputedStyle(card).borderLeftColor).toBe(token("line"));
  });
});

test("the composer grows with its lines, up to a height, and scrolls past it", async () => {
  const screen = await render(<Composer onSend={sent()} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  const two = box.element().getBoundingClientRect().height;
  await box.fill("one\ntwo\nthree\nfour\nfive");
  const five = box.element().getBoundingClientRect().height;
  expect(five).toBeGreaterThan(two);
  await box.fill(Array.from({ length: 40 }, (_, at) => `line ${at}`).join("\n"));
  const forty = box.element().getBoundingClientRect().height;
  expect(forty).toBeGreaterThan(five);
  expect(forty).toBeLessThanOrEqual(256);
  expect(box.element().scrollHeight).toBeGreaterThan(forty);
});

test("sent with the button, the composer keeps the focus in its words", async () => {
  const screen = await render(<Composer onSend={sent()} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("Draft the plan");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(box).toHaveValue("");
  expect(document.activeElement).toBe(box.element());
});

test("a question's answer field is read-only once sent, so the focus stays in it", async () => {
  const request: ArtifactrV1.DeferredRequest = {
    kind: "question",
    tool_call_id: "q9",
    tool_name: "ask",
    args: { question: "Which?" } as ArtifactrV1.Args,
  };
  const screen = await render(<Request request={request} onAnswer={sent()} />);
  const field = screen.getByRole("textbox", { name: "Answer" });
  await field.fill("That one");
  await userEvent.keyboard("{Enter}");
  await expect.element(field).toHaveAttribute("readonly");
  expect(document.activeElement).toBe(field.element());
});

test("a message refused comes back to the composer with the focus still in it", async () => {
  const screen = await render(<Composer onSend={sent("refused")} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("Draft the plan");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(box).toHaveValue("Draft the plan");
  await expect.element(screen.getByRole("alert")).toBeVisible();
  expect(document.activeElement).toBe(box.element());
});

test("Enter twice while a send is in flight sends once", async () => {
  const held: { settle?: () => void } = {};
  const onSend = vi.fn(
    () =>
      new Promise<{ outcome: "done" }>((resolve) => {
        held.settle = () => resolve({ outcome: "done" });
      }),
  );
  const screen = await render(<Composer onSend={onSend} />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("Draft the plan");
  await userEvent.keyboard("{Enter}");
  await box.fill("Another");
  await userEvent.keyboard("{Enter}");
  expect(onSend).toHaveBeenCalledTimes(1);
  held.settle?.();
  await expect.element(screen.getByRole("button", { name: "Send" })).not.toBeDisabled();
});

test("a long message is folded past its first lines, and opens whole; Copy copies all of it; a streaming one never folds", async () => {
  // Paragraphs, a blank line between: Markdown joins single lines into one.
  const lines = Array.from({ length: 60 }, (_, at) => `line ${at + 1}`).join("\n\n");
  const written = vi.spyOn(navigator.clipboard, "writeText").mockResolvedValue();
  const screen = await render(
    <Messages>
      <Message message={message({ content: lines })} author="Assistant" />
      <Streaming text={lines} author="Assistant" />
    </Messages>,
  );
  const whole = screen.getByRole("button", { name: "Show the whole message" });
  await expect.element(whole).toBeVisible();
  expect(screen.getByRole("button", { name: "Show the whole message" }).elements()).toHaveLength(1);
  const body = screen
    .getByRole("listitem", { name: "Assistant", exact: true })
    .element()
    .querySelector("[class*='max-h']") as Element;
  expect(getComputedStyle(body).overflow).toBe("hidden");
  await screen.getByRole("button", { name: "Copy as Markdown" }).click();
  expect(written).toHaveBeenLastCalledWith(lines);
  await whole.click();
  await expect.element(whole).not.toBeInTheDocument();
  expect(getComputedStyle(body).overflow).not.toBe("hidden");
});

test("the composer holds a way to attach at the start of its row, and hands dropped files to the page", async () => {
  const onFiles = vi.fn();
  const screen = await render(
    <Composer onSend={sent()} onFiles={onFiles} attach={<button type="button">Attach</button>} />,
  );
  const attach = screen.getByRole("button", { name: "Attach" }).element();
  const send = screen.getByRole("button", { name: "Send" }).element();
  expect(attach.compareDocumentPosition(send) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  const form = attach.closest("form") as HTMLFormElement;
  const files = new DataTransfer();
  files.items.add(new File(["hello"], "notes.txt", { type: "text/plain" }));
  form.dispatchEvent(
    new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: files }),
  );
  expect(form.dataset.over).toBe("");
  form.dispatchEvent(
    new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: files }),
  );
  expect(onFiles).toHaveBeenCalledTimes(1);
  const given = onFiles.mock.calls[0]?.[0] as FileList;
  expect(given[0]?.name).toBe("notes.txt");
  expect(form.dataset.over).toBeUndefined();
});

test("a page's actions menu holds thumbs as checked items, then asks why", async () => {
  const onThumbs = sent();
  const screen = await render(
    <ActionsMenu
      label="Artifact actions"
      given={{ up: true, comment: null }}
      onThumbs={onThumbs}
    />,
  );
  await screen.getByRole("button", { name: "Artifact actions" }).click();
  const menu = screen.getByRole("menu");
  await expect
    .element(menu.getByRole("menuitemcheckbox", { name: "Helpful" }))
    .toHaveAttribute("aria-checked", "true");
  await menu.getByRole("menuitemcheckbox", { name: "Not helpful" }).click();
  expect(onThumbs).toHaveBeenLastCalledWith(false, null);
  await screen.getByRole("textbox", { name: "Why? (optional)" }).fill("It missed the date");
  await screen.getByRole("button", { name: "Add" }).click();
  expect(onThumbs).toHaveBeenLastCalledWith(false, "It missed the date");
});
