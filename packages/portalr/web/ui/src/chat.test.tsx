import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import { describe, expect, onTestFinished, test, vi } from "vitest";
import { page, userEvent } from "vitest/browser";
import { render } from "vitest-browser-react";
import {
  ActionsMenu,
  CommandButton,
  Composer,
  Message,
  Messages,
  ModeSwitch,
  ProposalCard,
  proposalTitle,
  proposedOn,
  Request,
  RunStatus,
  RunStrip,
  Streaming,
  Thumbs,
  unhidden,
} from "./chat";
import { IntegrationsContext } from "./integrations";
import { contrast, token } from "./test/colours";
import { ProposalLine } from "./tray";

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

test("the reader's words sit on the quiet wash at the end of the line, the agent's unboxed at its start", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="You" mine />
      <Message message={message({ id: "msg_2" })} author="Assistant" />
    </Messages>,
  );
  const mine = screen.getByRole("listitem", { name: "You" }).element();
  const theirs = screen.getByRole("listitem", { name: "Assistant" }).element();
  expect(getComputedStyle(mine).alignSelf).toBe("flex-end");
  expect(getComputedStyle(mine).alignItems).toBe("flex-end");
  expect(getComputedStyle(theirs).alignSelf).toBe("flex-start");
  const body = (item: Element) => getComputedStyle(item.querySelector(":scope > div") as Element);
  expect(body(mine).backgroundColor).toBe(token("subtle"));
  expect(body(theirs).backgroundColor).toBe("rgba(0, 0, 0, 0)");
  expect(body(theirs).borderTopWidth).toBe("0px");
  // The name above each: the reader's in the ink, the agent's quieter.
  expect(getComputedStyle(screen.getByText("You").element()).color).toBe(token("fg"));
  expect(getComputedStyle(screen.getByText("Assistant").element()).color).toBe(token("muted"));
});

for (const dir of ["ltr", "rtl"] as const) {
  test(`in ${dir}, the reader's message meets the line's end and the agent's its start`, async () => {
    const screen = await render(
      <div dir={dir} style={{ width: "400px" }}>
        <Messages>
          <Message message={message({ content: "Hi" })} author="You" mine />
          <Message message={message({ id: "msg_2", content: "Hello" })} author="Assistant" />
          <Message message={message({ id: "msg_3", content: "Later" })} author="You" mine sending />
        </Messages>
      </div>,
    );
    const log = screen.getByRole("list").element().getBoundingClientRect();
    const [mine, theirs, queued] = screen
      .getByRole("listitem")
      .elements()
      .map((item) => item.getBoundingClientRect());
    const end = (box: DOMRect) => (dir === "ltr" ? log.right - box.right : box.left - log.left);
    const start = (box: DOMRect) => (dir === "ltr" ? box.left - log.left : log.right - box.right);
    expect(Math.abs(end(mine as DOMRect))).toBeLessThan(1);
    expect(Math.abs(end(queued as DOMRect))).toBeLessThan(1);
    expect(Math.abs(start(theirs as DOMRect))).toBeLessThan(1);
    expect(start(mine as DOMRect)).toBeGreaterThan(100);
  });
}

test("a long word in the reader's message wraps inside its bubble", async () => {
  const word = "x".repeat(300);
  const screen = await render(
    <div style={{ width: "320px" }}>
      <Messages>
        <Message message={message({ content: `https://example.test/${word}` })} author="You" mine />
      </Messages>
    </div>,
  );
  const item = screen.getByRole("listitem", { name: "You" }).element();
  const bubble = item.querySelector(":scope > div") as HTMLElement;
  expect(bubble.scrollWidth).toBeLessThanOrEqual(bubble.clientWidth);
  expect(item.getBoundingClientRect().width).toBeLessThanOrEqual(320 * 0.85 + 1);
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

test("before its first words a run draws nothing: the strip is the one sign that it works", async () => {
  const screen = await render(
    <Messages>
      <Streaming text="" author="Assistant" />
    </Messages>,
  );
  expect(screen.getByRole("listitem").elements()).toHaveLength(0);
  expect(screen.container.querySelector(".animate-pulse")).toBeNull();
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

test("a kept draft comes back after a reload, is let go once sent, and keeps its own thread", async () => {
  sessionStorage.removeItem("portalr:draft:th_1");
  const first = await render(<Composer onSend={sent()} draft="th_1" />);
  await first.getByRole("textbox", { name: "Message" }).fill("Half a thought");
  await first.unmount();
  const other = await render(<Composer onSend={sent()} draft="th_2" />);
  await expect.element(other.getByRole("textbox", { name: "Message" })).toHaveValue("");
  await other.unmount();
  const again = await render(<Composer onSend={sent()} draft="th_1" />);
  const box = again.getByRole("textbox", { name: "Message" });
  await expect.element(box).toHaveValue("Half a thought");
  await box.click();
  await userEvent.keyboard("{Enter}");
  await vi.waitFor(() => expect(sessionStorage.getItem("portalr:draft:th_1")).toBeNull());
});

test("a message on its way stays kept until it is answered", async () => {
  sessionStorage.removeItem("portalr:draft:th_5");
  let answer: (sent: { outcome: "done" }) => void = () => {};
  const onSend = vi.fn(() => new Promise<{ outcome: "done" }>((settle) => (answer = settle)));
  const screen = await render(<Composer onSend={onSend} draft="th_5" />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("On its way");
  await box.click();
  await userEvent.keyboard("{Enter}");
  await expect.element(box).toHaveValue("");
  expect(sessionStorage.getItem("portalr:draft:th_5")).toBe("On its way");
  answer({ outcome: "done" });
  await vi.waitFor(() => expect(sessionStorage.getItem("portalr:draft:th_5")).toBeNull());
});

test("Reload chosen in a new version's offer leaves a kept draft without asking", async () => {
  const leave = () => {
    const event = new Event("beforeunload", { cancelable: true });
    dispatchEvent(event);
    return event.defaultPrevented;
  };
  const kept = await render(<Composer onSend={sent()} draft="th_3" />);
  await kept.getByRole("textbox", { name: "Message" }).fill("Half a thought");
  await vi.waitFor(() => expect(leave()).toBe(true));
  dispatchEvent(new Event("portalr:reload"));
  expect(leave()).toBe(false);
  await kept.unmount();
  sessionStorage.removeItem("portalr:draft:th_3");
  // One not kept would lose its words: it still asks.
  const unkept = await render(<Composer onSend={sent()} />);
  await unkept.getByRole("textbox", { name: "Message" }).fill("Half a thought");
  dispatchEvent(new Event("portalr:reload"));
  await vi.waitFor(() => expect(leave()).toBe(true));
});

test("storage refused, a draft still lives as long as the page", async () => {
  onTestFinished(() => {
    vi.restoreAllMocks();
  });
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new DOMException("refused", "SecurityError");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("refused", "SecurityError");
  });
  const screen = await render(<Composer onSend={sent()} draft="th_4" />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("Half a thought");
  await expect.element(box).toHaveValue("Half a thought");
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

test("thumbs the application doesn't define say so, rather than that the server refused", async () => {
  const none = vi.fn(async () => ({
    outcome: "refused" as const,
    result: {
      rejection: {
        type: "not_found",
        message: "feedback type thumbs does not exist",
        entity: "feedback type",
        id: "thumbs",
      },
    },
  }));
  const screen = await render(<Thumbs given={null} onThumbs={none} />);
  await screen.getByRole("button", { name: "Helpful" }).click();
  await expect
    .element(screen.getByRole("alert"))
    .toHaveTextContent("Thumbs aren't available in this workspace.");
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

  test("open, it carries a tick in the working colour inside its edge; answered, it doesn't", async () => {
    const screen = await render(<Request request={asked} onAnswer={sent()} />);
    const card = screen.getByText("The agent asks").element().parentElement as Element;
    const tick = () => getComputedStyle(card, "::before");
    expect(tick().backgroundColor).toBe(token("accent"));
    expect(tick().height).toBe("20px");
    expect(getComputedStyle(card).borderLeftColor).toBe(token("line"));
    await screen.rerender(<Request request={asked} onAnswer={sent()} answeredBy="Alice" />);
    expect(tick().content).toBe("none");
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

const run = (status: Artifactr.Run["status"], requests: ArtifactrV1.DeferredRequest[] = []) =>
  ({
    id: "run_1",
    threadId: "t_1",
    status,
    tools: {},
    text: "",
    live: live(),
    requests,
    answered: [],
    started: 1,
    startedAt: "2026-10-20T00:00:00Z",
    ended: null,
    error: null,
  }) as unknown as Artifactr.Run;

const live = (change: Partial<Artifactr.Live> = {}): Artifactr.Live => ({
  phase: "starting",
  tool: null,
  calls: 0,
  argsChars: 0,
  thinking: "",
  thoughtMs: 0,
  outputChars: 0,
  since: 0,
  at: 0,
  part: null,
  reply: "pending",
  truncated: false,
  framed: false,
  usage: null,
  ...change,
});

/** The strip over a running turn whose live state is `change`, at `now`. */
const strip = (change: Partial<Artifactr.Live>, now: Date, more = {}) => (
  <RunStrip run={{ ...run("running"), live: live(change) }} onStop={sent()} now={now} {...more} />
);

test("the strip says what the turn is doing, in one status, and how long since its last frame once that is a while", async () => {
  const now = new Date("2026-10-20T00:01:05Z");
  const at = now.getTime() - 5000;
  const screen = await render(
    strip({ phase: "tool", tool: "create_app", argsChars: 12_300, at }, now),
  );
  const group = screen.getByRole("group", { name: "This turn" });
  await expect.element(group.getByText("Preparing a create_app call, 12 KB")).toBeVisible();
  expect(group.getByRole("status").elements()).toHaveLength(1);
  await expect
    .element(group.getByRole("status"))
    .toHaveTextContent("Working: Preparing a create_app call, 12 KB");
  await expect.element(group.getByRole("button", { name: "Stop" })).toBeVisible();
  // The clock ticks outside the status.
  expect(group.getByRole("status").element().textContent).not.toContain("1:05");
  await screen.rerender(strip({ phase: "tool", tool: "create_app", calls: 1, at }, now));
  await expect.element(group.getByText("Running create_app")).toBeVisible();
  await screen.rerender(strip({ phase: "writing", at: now.getTime() - 40_000 }, now));
  await expect
    .element(group.getByText("Writing the reply, 40 s since the last output"))
    .toBeVisible();
  await screen.rerender(strip({ phase: "thinking", at }, now));
  await expect.element(group.getByText("Thinking")).toBeVisible();
  await screen.rerender(strip({ at: now.getTime() - 21_000 }, now));
  await expect
    .element(group.getByText("Waiting on the model, 21 s since the last output"))
    .toBeVisible();
  // Phases that go by in a blink are announced at most every few seconds: the last is pending.
  expect(group.getByRole("status").element().textContent).not.toContain("21 s");
});

test("the strip counts the turn's tokens in one line, each estimated and named in full", async () => {
  const now = new Date();
  const screen = await render(strip({ outputChars: 401 }, now, { history: 4000 }));
  const group = screen.getByRole("group", { name: "This turn" });
  // One line, there from the first, with nothing to open (portalr ADR-0092).
  await expect.element(group.getByText("in ~1,000 · out ~101")).toBeVisible();
  expect(group.getByRole("button", { name: "Tokens" }).elements()).toHaveLength(0);
  await expect
    .element(group.getByText("Input tokens, estimated: 1,000. Output tokens, estimated: 101"))
    .toBeInTheDocument();
  // Never broken across lines, and never announced.
  const line = group.getByText("in ~1,000 · out ~101").element().parentElement as HTMLElement;
  expect(getComputedStyle(line).whiteSpace).toBe("nowrap");
  expect(line.closest("[role=status], [aria-live]")).toBeNull();
  await screen.rerender(strip({ outputChars: 401 }, now, { history: null }));
  await expect.element(group.getByText("out ~101")).toBeVisible();
  expect(group.getByText(/^in ~/).elements()).toHaveLength(0);
});

test("once the provider has counted, the line is exact, with the cache and reasoning where any, and the model", async () => {
  const now = new Date();
  const usage = {
    requests: 1,
    input_tokens: 1030,
    output_tokens: 40,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    reasoning_tokens: 0,
    model: "glm-4.7",
  };
  const screen = await render(strip({ outputChars: 401, usage }, now, { history: 4000 }));
  const group = screen.getByRole("group", { name: "This turn" });
  await expect.element(group.getByText("in 1,030 · out 40 · glm-4.7")).toBeVisible();
  await expect
    .element(group.getByText("Input tokens: 1,030. Output tokens: 40. Model: glm-4.7"))
    .toBeInTheDocument();
  // None read from the cache, written to it, or spent reasoning: the line says none of them.
  expect(group.getByText(/(cached|cache write|reasoning) /).elements()).toHaveLength(0);
  expect(group.getByText(/~/).elements()).toHaveLength(0);
  const more = { cache_read_tokens: 800, cache_write_tokens: 200, reasoning_tokens: 12 };
  await screen.rerender(strip({ usage: { ...usage, ...more, model: null } }, now));
  await expect
    .element(group.getByText("in 1,030 · out 40 · cached 800 · cache write 200 · reasoning 12"))
    .toBeVisible();
  await expect.element(group.getByText(/Cached input tokens: 800/)).toBeInTheDocument();
  await expect.element(group.getByText(/Reasoning tokens: 12/)).toBeInTheDocument();
  expect(group.getByText(/glm-4\.7/).elements()).toHaveLength(0);
});

test("a count that fits one line at a phone's width does, with the cache and reasoning in it", async () => {
  await page.viewport(390, 700);
  const usage = {
    requests: 1,
    input_tokens: 32_369,
    output_tokens: 6925,
    cache_read_tokens: 0,
    cache_write_tokens: 0,
    reasoning_tokens: 4955,
    model: "default",
  };
  const screen = await render(strip({ usage }, new Date()));
  const line = screen.getByText("in 32,369 · out 6,925 · reasoning 4,955 · default");
  await expect.element(line).toBeVisible();
  const box = line.element().parentElement as HTMLElement;
  expect(box.scrollWidth).toBeLessThanOrEqual(box.clientWidth);
  expect(line.element().getBoundingClientRect().height).toBeLessThan(20);
});

test("what streams is never announced as it grows: only the posted message is", async () => {
  const screen = await render(
    <Messages>
      <Streaming text="Hel" live={live({ phase: "writing" })} author="Assistant" />
    </Messages>,
  );
  const writing = screen.getByRole("listitem", { name: "Assistant is writing" });
  await expect.element(writing).toHaveAttribute("aria-live", "off");
  const word = writing.getByText("Hel").element();
  expect(word.closest("[aria-live]")).toBe(writing.element());
  await screen.rerender(
    <Messages>
      <Streaming text="Hello there" live={live({ phase: "writing" })} author="Assistant" />
    </Messages>,
  );
  await expect.element(writing.getByText("Hello there")).toBeVisible();
  expect(
    writing
      .element()
      .querySelectorAll("[role=status], [role=alert], [aria-live=polite], [aria-live=assertive]"),
  ).toHaveLength(0);
  expect(screen.getByRole("log").element().getAttribute("aria-live")).toBeNull();
});

test("the model's thinking is folded under how long it has thought, and says it isn't kept", async () => {
  const screen = await render(
    <Messages>
      <Streaming
        text=""
        live={live({ phase: "thinking", thinking: "Let me see." })}
        author="Assistant"
      />
    </Messages>,
  );
  const button = screen.getByRole("button", { name: "Thinking…" });
  await expect.element(button).toHaveAttribute("aria-expanded", "false");
  await expect.element(screen.getByText("Let me see.")).not.toBeVisible();
  await button.click();
  await expect.element(button).toHaveAttribute("aria-expanded", "true");
  await expect.element(screen.getByText("Let me see.")).toBeVisible();
  await expect
    .element(screen.getByText("Thinking isn't kept: it goes when the page does."))
    .toBeVisible();
  await screen.rerender(
    <Messages>
      <Streaming
        text="So,"
        live={live({ phase: "writing", thinking: "Let me see.", thoughtMs: 12_400 })}
        author="Assistant"
      />
    </Messages>,
  );
  await expect.element(screen.getByRole("button", { name: "Thought for 12 s" })).toBeVisible();
});

test("a turn that was stopped, or failed, keeps what it streamed, quietly, and says so", async () => {
  const screen = await render(
    <Messages>
      <Streaming
        text="Half a rep"
        live={live({ thinking: "Hmm", thoughtMs: 2000 })}
        ended="stopped"
        author="Assistant"
      />
    </Messages>,
  );
  const left = screen.getByRole("listitem", { name: "Assistant didn't finish" });
  await expect.element(left).not.toHaveAttribute("aria-busy");
  await expect.element(left.getByText("Half a rep")).toBeVisible();
  expect(left.getByText("Stopped here.").elements()).toHaveLength(0); // the log's own line says it
  await expect.element(left.getByRole("button", { name: "Thought for 2 s" })).toBeVisible();
  // What it streamed is read as any message is: never faded.
  expect(getComputedStyle(left.element()).opacity).toBe("1");
});

test("the strip over a turn says how it goes, for how long, and offers Stop while it works", async () => {
  const onStop = sent();
  const now = new Date("2026-10-20T00:01:05Z");
  const screen = await render(<RunStrip run={run("running")} onStop={onStop} now={now} />);
  const strip = screen.getByRole("group", { name: "This turn" });
  // "Working" at once; what it is doing joins it once the add-on that words it has loaded.
  await expect.poll(() => strip.getByRole("status").element().textContent).toMatch(/^Working/);
  await expect.element(strip.getByText("for 1:05")).toBeVisible();
  await strip.getByRole("button", { name: "Stop" }).click();
  expect(onStop).toHaveBeenCalledOnce();
  expect(strip.getByRole("button", { name: "Go to the question" }).elements()).toHaveLength(0);
});

test("the strip over a paused turn offers the way to its question, and no Stop", async () => {
  const onQuestion = vi.fn();
  const screen = await render(
    <RunStrip run={run("paused")} onStop={sent()} onQuestion={onQuestion} now={new Date()} />,
  );
  const strip = screen.getByRole("group", { name: "This turn" });
  await expect.element(strip.getByRole("status")).toHaveTextContent("Waiting for you");
  expect(strip.getByRole("button", { name: "Stop" }).elements()).toHaveLength(0);
  await strip.getByRole("button", { name: "Go to the question" }).click();
  expect(onQuestion).toHaveBeenCalledOnce();
});

test("away from the end, the way back to the latest is offered once more arrives, and not before", async () => {
  const lines = (count: number, from = 0) =>
    Array.from({ length: count }, (_, at) => (
      <li key={from + at} style={{ height: "40vh" }}>
        Message {from + at + 1}
      </li>
    ));
  const screen = await render(<Messages>{lines(6)}</Messages>);
  window.scrollTo(0, document.documentElement.scrollHeight);
  await expect.poll(() => window.scrollY).toBeGreaterThan(0);
  window.scrollTo(0, 0);
  await expect.poll(() => window.scrollY).toBe(0);
  // Away, but nothing new: nothing is offered.
  await new Promise((settled) => setTimeout(settled, 100));
  expect(screen.getByRole("button", { name: "Jump to latest" }).elements()).toHaveLength(0);
  await screen.rerender(<Messages>{lines(7)}</Messages>);
  const jump = screen.getByRole("button", { name: "Jump to latest" });
  await expect.element(jump).toBeVisible();
  await jump.click();
  await expect.element(jump).not.toBeInTheDocument();
  expect(document.activeElement?.textContent).toBe("Message 7");
  expect(window.scrollY).toBeGreaterThan(0);
});

test("the mode switch sends the mode chosen, and says when it is refused", async () => {
  const onChange = sent("refused");
  const screen = await render(<ModeSwitch mode="edit" onChange={onChange} />);
  const group = screen.getByRole("radiogroup", { name: "Agent mode" });
  await expect.element(group.getByRole("radio", { name: "Auto" })).toBeChecked();
  await group.getByRole("radio", { name: "Ask" }).click();
  expect(onChange).toHaveBeenCalledWith("suggest");
  await expect.element(screen.getByRole("alert")).toBeVisible();
});

test("where the pointer hovers, a message's actions show as it rests on the message, or the keyboard reaches them", async () => {
  const screen = await render(
    <Messages>
      <Message message={message()} author="Assistant" thumbs={null} onThumbs={sent()} />
    </Messages>,
  );
  const item = screen.getByRole("listitem", { name: "Assistant" });
  const copy = screen.getByRole("button", { name: "Copy as Markdown" });
  const row = copy.element().parentElement as HTMLElement;
  if (!matchMedia("(hover: hover)").matches) {
    return; // a pointer that can't hover has the menu instead: the test below
  }
  await expect.poll(() => getComputedStyle(row).opacity).toBe("0");
  await userEvent.hover(item);
  await expect.poll(() => getComputedStyle(row).opacity).toBe("1");
  await userEvent.unhover(item);
  await expect.poll(() => getComputedStyle(row).opacity).toBe("0");
  await userEvent.tab();
  await expect.element(copy).toHaveFocus();
  await expect.poll(() => getComputedStyle(row).opacity).toBe("1");
});

test("where the pointer can't hover, a message's actions are a menu, which a long press opens too", async () => {
  const onThumbs = sent();
  const screen = await render(
    <Messages>
      <Message message={message()} author="Assistant" thumbs={null} onThumbs={onThumbs} coarse />
    </Messages>,
  );
  expect(screen.getByRole("button", { name: "Copy as Markdown" }).elements()).toHaveLength(0);
  // No "…" under every message (portalr ADR-0085): its button is a screen reader's alone, and
  // nothing is drawn beneath the words.
  const trigger = screen.getByRole("button", { name: "Message actions" });
  const item = screen.getByRole("listitem").element();
  const drawn = [...item.querySelectorAll("button")].filter(
    (button) => button.closest(".sr-only") === null,
  );
  expect(drawn).toHaveLength(0);
  trigger.element().dispatchEvent(new MouseEvent("click", { bubbles: true }));
  const menu = screen.getByRole("menu");
  await expect.element(menu.getByRole("menuitem", { name: "Copy as Markdown" })).toBeVisible();
  await menu.getByRole("menuitemcheckbox", { name: "Helpful" }).click();
  expect(onThumbs).toHaveBeenLastCalledWith(true, null);
  await expect.element(screen.getByRole("menu")).not.toBeInTheDocument();
  const bubble = screen.getByText("ready").element().closest("li > div") as HTMLElement;
  bubble.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
  await expect.element(screen.getByRole("menu")).toBeVisible();
  bubble.dispatchEvent(new PointerEvent("pointerup", { bubbles: true }));
});

test("text dragged over the composer is left to the browser: only files are taken", async () => {
  const onFiles = vi.fn();
  const screen = await render(<Composer onSend={sent()} onFiles={onFiles} />);
  const form = screen
    .getByRole("button", { name: "Send" })
    .element()
    .closest("form") as HTMLFormElement;
  const text = new DataTransfer();
  text.setData("text/plain", "words");
  form.dispatchEvent(
    new DragEvent("dragover", { bubbles: true, cancelable: true, dataTransfer: text }),
  );
  expect(form.dataset.over).toBeUndefined();
  form.dispatchEvent(
    new DragEvent("drop", { bubbles: true, cancelable: true, dataTransfer: text }),
  );
  expect(onFiles).not.toHaveBeenCalled();
});

test("asked to keep them, the composer gives the words back when the connection closes too", async () => {
  const screen = await render(<Composer onSend={sent("closed")} keep />);
  const box = screen.getByRole("textbox", { name: "Message" });
  await box.fill("Plan the launch");
  await screen.getByRole("button", { name: "Send" }).click();
  await expect.element(box).toHaveValue("Plan the launch");
});

test("in the actions menu, the thumb already given is given: choosing it again sends nothing", async () => {
  const onThumbs = sent();
  const screen = await render(
    <ActionsMenu
      label="Artifact actions"
      given={{ up: true, comment: null }}
      onThumbs={onThumbs}
    />,
  );
  await screen.getByRole("button", { name: "Artifact actions" }).click();
  await screen.getByRole("menuitemcheckbox", { name: "Helpful" }).click();
  expect(onThumbs).not.toHaveBeenCalled();
});

test("the whole-message button stays as it is pressed, says its state, and shows less again", async () => {
  const lines = Array.from({ length: 60 }, (_, at) => `Line ${at + 1}`).join("\n\n");
  const screen = await render(
    <Messages>
      <Message message={message({ content: lines })} author="Assistant" />
    </Messages>,
  );
  const button = screen.getByRole("button", { name: "Show the whole message" });
  await expect.element(button).toHaveAttribute("aria-expanded", "false");
  await button.click();
  const less = screen.getByRole("button", { name: "Show less" });
  await expect.element(less).toHaveAttribute("aria-expanded", "true");
  await expect.element(less).toHaveFocus();
  await less.click();
  await expect
    .element(screen.getByRole("button", { name: "Show the whole message" }))
    .toBeVisible();
});

test("the log holds the messages alone: Jump to latest sits outside it", async () => {
  const lines = (count: number) =>
    Array.from({ length: count }, (_, at) => (
      <li key={at} style={{ height: "40vh" }}>
        Message {at + 1}
      </li>
    ));
  const screen = await render(<Messages>{lines(6)}</Messages>);
  window.scrollTo(0, 0);
  await screen.rerender(<Messages>{lines(7)}</Messages>);
  const jump = screen.getByRole("button", { name: "Jump to latest" });
  await expect.element(jump).toBeVisible();
  expect(jump.element().closest("[role=log]")).toBeNull();
});

test("what streamed says where its start is missing, is read as the reply is before a tool call, and a thought of unknown length has none", async () => {
  const screen = await render(
    <Messages>
      <Streaming
        text="and so on."
        live={live({
          phase: "tool",
          tool: "look",
          thinking: "mm",
          thoughtMs: null,
          truncated: true,
          reply: "stale",
        })}
        author="Assistant"
      />
    </Messages>,
  );
  const item = screen.getByRole("listitem", { name: "Assistant is writing" });
  const words = item.getByText("…and so on.");
  await expect.element(words).toBeVisible(); // its start is missing
  await expect.element(item.getByRole("button", { name: "Thought", exact: true })).toBeVisible();
  // Words before a tool call are not the reply, and are as legible as it: none of what holds them
  // is faded, and their colour is the page's own.
  for (let at: Element | null = words.element(); at; at = at.parentElement) {
    expect(getComputedStyle(at).opacity).toBe("1");
  }
  expect(getComputedStyle(words.element()).color).toBe(getComputedStyle(document.body).color);
  await screen.rerender(
    <Messages>
      <Streaming
        text="The reply."
        live={live({ phase: "writing", thinking: "mm", thoughtMs: 400 })}
        author="Assistant"
      />
    </Messages>,
  );
  expect(item.getByText(/^…/).elements()).toHaveLength(0);
  await expect.element(item.getByRole("button", { name: "Thought for a moment" })).toBeVisible();
});

test("the strip says how a turn ended in the same status", async () => {
  const now = new Date();
  const screen = await render(
    strip({ phase: "writing", at: now.getTime() }, now, { history: 400 }),
  );
  const group = screen.getByRole("group", { name: "This turn" });
  await expect.element(group.getByText(/in ~100/)).toBeVisible();
  const status = group.getByRole("status").element();
  await screen.rerender(
    <RunStrip run={{ ...run("completed"), live: live() }} onStop={sent()} now={now} />,
  );
  expect(group.getByRole("status").element()).toBe(status); // the same one, so it says it
  await expect.poll(() => status.textContent).toBe("Done");
  expect(group.getByRole("button", { name: "Stop" }).elements()).toHaveLength(0);
  expect(group.element().querySelector(".w-full")).toBeNull();
  await screen.rerender(<RunStrip run={{ ...run("stopped"), live: live() }} now={now} />);
  await expect.poll(() => status.textContent).toBe("Stopped");
});

test("a turn that ended with no words draws no bubble, and says it didn't finish", async () => {
  const screen = await render(
    <Messages>
      <Streaming text="" live={live({ thinking: "mm" })} ended="failed" author="Assistant" />
    </Messages>,
  );
  const item = screen.getByRole("listitem", { name: "Assistant didn't finish" });
  await expect.element(item).toBeVisible();
  // No bubble under the author, and no dots in one.
  expect(item.element().querySelector(":scope > div.max-w-full")).toBeNull();
  expect(item.element().querySelector(".animate-pulse, .h-6")).toBeNull();
});

test("a thinking part still open as the turn ended counts to its last frame", async () => {
  const screen = await render(
    <Messages>
      <Streaming
        text=""
        live={live({ phase: "thinking", thinking: "mm", thoughtMs: 1000, since: 1000, at: 3000 })}
        ended="failed"
        author="Assistant"
      />
    </Messages>,
  );
  await expect.element(screen.getByRole("button", { name: "Thought for 3 s" })).toBeVisible();
});

test("thinking is isolated, so a direction mark in it can't reorder what follows", async () => {
  const screen = await render(
    <Messages>
      <Streaming
        text=""
        live={live({ phase: "thinking", thinking: "a\u202eb" })}
        author="Assistant"
      />
    </Messages>,
  );
  await screen.getByRole("button", { name: "Thinking…" }).click();
  const shown = screen.getByText("a\u202eb");
  await expect.element(shown).toBeVisible();
  expect(shown.element().tagName).toBe("BDI");
});

test("on a narrow phone, the strip's button wraps under it rather than squeezing it", async () => {
  await page.viewport(320, 700);
  const now = new Date();
  const paused = { ...run("paused"), live: live() };
  const screen = await render(
    <RunStrip run={paused} onStop={sent()} onQuestion={() => {}} now={now} />,
  );
  const group = screen.getByRole("group", { name: "This turn" });
  const way = group.getByRole("button", { name: "Go to the question" });
  await expect.element(way).toBeVisible();
  const strip = group.element();
  expect(strip.scrollWidth).toBeLessThanOrEqual(strip.clientWidth);
  expect(way.element().getBoundingClientRect().right).toBeLessThanOrEqual(window.innerWidth);
});

test("the strip is one line: its state, what it does, its clock and Stop, and the clock's place never moves as it ticks", async () => {
  await page.viewport(390, 700);
  const at = Date.now();
  const screen = await render(
    strip({ phase: "tool", tool: "create_artifact", calls: 0, at }, new Date(at), {}),
  );
  const group = screen.getByRole("group", { name: "This turn" });
  const stop = group.getByRole("button", { name: "Stop" });
  await expect.element(stop).toBeVisible();
  await expect.element(group.getByText("Preparing a create_artifact call")).toBeVisible();
  const row = group.element().firstElementChild as HTMLElement;
  // The box that holds "for" (said, not shown) and the time.
  const clock = group.getByText(/^for /, { exact: true }).element().parentElement as HTMLElement;
  const before = Math.round(clock.getBoundingClientRect().right);
  expect(getComputedStyle(clock).fontVariantNumeric).toBe("normal");
  // A minute's carry, from 9:59 to 10:00, moves nothing.
  const started = new Date(Date.parse("2026-10-20T00:00:00Z"));
  await screen.rerender(
    <RunStrip
      run={{ ...run("running"), live: live({ phase: "tool", tool: "create_artifact", at }) }}
      onStop={sent()}
      now={new Date(started.getTime() + 599_000)}
    />,
  );
  await expect.element(group.getByText(/9:59/)).toBeVisible();
  // Its digits tabular and its colon not, so it reads "9:59", not "9 : 59" (as `Num` sets them).
  const digits = [...clock.querySelectorAll(".tabular-nums")];
  expect(digits.map((each) => each.textContent)).toEqual(["9", "59"]);
  expect(getComputedStyle(digits[0] as Element).fontVariantNumeric).toBe("tabular-nums");
  const nine = Math.round(group.getByText(/9:59/).element().getBoundingClientRect().right);
  await screen.rerender(
    <RunStrip
      run={{ ...run("running"), live: live({ phase: "tool", tool: "create_artifact", at }) }}
      onStop={sent()}
      now={new Date(started.getTime() + 600_000)}
    />,
  );
  await expect.element(group.getByText(/10:00/)).toBeVisible();
  expect(Math.round(group.getByText(/10:00/).element().getBoundingClientRect().right)).toBe(nine);
  expect(row.getBoundingClientRect().height).toBeLessThanOrEqual(44);
  expect(before).toBeGreaterThan(0);
});

test("the model's thinking streams into its fold while the run is in flight", async () => {
  const screen = await render(
    <Messages>
      <Streaming
        text=""
        live={live({ phase: "thinking", thinking: "Let me" })}
        author="Assistant"
      />
    </Messages>,
  );
  await screen.getByRole("button", { name: "Thinking…" }).click();
  const thought = () => screen.getByText(/^Let me/).element().textContent;
  await expect.poll(thought).toBe("Let me");
  await screen.rerender(
    <Messages>
      <Streaming
        text=""
        live={live({ phase: "thinking", thinking: "Let me see how this goes" })}
        author="Assistant"
      />
    </Messages>,
  );
  await expect.poll(thought).toBe("Let me see how this goes");
  // Still open, still thinking, and still no dots: the fold and the strip say it.
  await expect
    .element(screen.getByRole("button", { name: "Thinking…" }))
    .toHaveAttribute("aria-expanded", "true");
  expect(screen.container.querySelector(".animate-pulse")).toBeNull();
});

test("a stopped turn's kept words render as Markdown, its list cut mid-item and all", async () => {
  const screen = await render(
    <Messages>
      <Streaming
        text={"I've drafted it:\n\n1. A hero with the tagline\n2. Pricing, three"}
        live={live({ phase: "writing" })}
        ended="stopped"
        author="Assistant"
      />
    </Messages>,
  );
  const item = screen.getByRole("listitem", { name: "Assistant didn't finish" });
  const list = item.getByRole("list");
  await expect.element(list).toBeVisible();
  expect(list.element().tagName).toBe("OL");
  await expect.element(list.getByText("A hero with the tagline")).toBeVisible();
  await expect.element(list.getByText("Pricing, three")).toBeVisible();
  expect(item.element().textContent).not.toContain("\\n");
});

test("a proposal that was decided is one line of the thread: whether it was accepted or rejected, and what it was", async () => {
  const screen = await render(
    <Messages>
      <ProposalLine proposal={proposal({ status: "accept" })} />
      <ProposalLine proposal={proposal({ id: "prop_2", status: "reject" })} />
    </Messages>,
  );
  const what = proposalTitle(proposal());
  const [accepted, rejected] = screen.getByRole("listitem").elements();
  expect(accepted?.textContent).toBe(`Accepted${what}`);
  expect(rejected?.textContent).toBe(`Rejected${what}`);
  // Slim: one line of words, no buttons and no landmark of its own: nothing of its card.
  for (const line of [accepted, rejected]) {
    expect(line?.getBoundingClientRect().height).toBeLessThan(36);
    expect(line?.querySelector("button, section")).toBeNull();
  }
  expect(screen.getByRole("region").elements()).toHaveLength(0);
});
