/**
 * The chat's look, pinned by screenshots (portalr ADR-0053): the reader's messages and the
 * agent's on their sides, a run's tool calls with one open, the agent's questions, open and
 * answered, a turn that is thinking, and one that failed. Wide and narrow, in each scheme. Like the
 * gallery's, the baselines are Linux's, made in CI.
 */

import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import { expect, onTestFinished, test } from "vitest";
import { commands, page } from "vitest/browser";
import { render } from "vitest-browser-react";
import { Message, Messages, Streaming } from "./chat";
import { Questions } from "./questions";
import { RunFailed } from "./run-failed";
import { dark } from "./test/colours";
import { ToolCall, ToolCalls } from "./tool-call";

const sent = async () => ({ outcome: "done" }) as const;

const message = (id: string, content: string, user: boolean): Artifactr.Message => ({
  id,
  seq: 1,
  actor: user ? { kind: "user", id: "alice" } : { kind: "agent", thread_id: "t", run_id: "r" },
  content,
  kind: "message",
  runId: user ? null : "r",
  feedback: [],
});

const ASKED: ArtifactrV1.DeferredRequest = {
  kind: "question",
  tool_call_id: "q1",
  tool_name: "ask_user",
  args: {
    questions: [
      {
        question: "Which week should the launch note cover?",
        header: "Launch week",
        options: [
          { label: "This week", description: "The current week", recommended: true },
          { label: "Next week", description: "The following week" },
        ],
        other: true,
      },
      {
        question: "Which topics should it cover?",
        header: "Topics",
        options: [
          { label: "What shipped", description: "Highlights and scope", recommended: true },
          { label: "Metrics", description: "Adoption and feedback" },
          { label: "Next steps", description: "What comes after" },
        ],
        multiple: true,
      },
    ],
  } as ArtifactrV1.Args,
};

const tool = (name: string, status: string, result: string): Artifactr.Tool => ({
  name,
  status,
  args: '{"kind": "note", "data": {"text": "Launching next week."}}',
  result,
  argsCut: false,
  resultCut: false,
  seq: 1,
});

function Thread() {
  return (
    <div data-testid="chat" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <Messages>
        <Message message={message("m1", "Draft the launch note.", true)} author="You" mine />
        <li>
          <Questions request={ASKED} onAnswer={sent} focus={false} />
        </li>
        <ToolCalls>
          <ToolCall tool={tool("create_artifact", "ok", "Done: note_1 is now at version 1.")} />
          <ToolCall tool={tool("draft_rule", "retry", "rule\n  Input should be an object")} />
        </ToolCalls>
        <Message
          message={message("m2", "The launch note is **drafted**.", false)}
          author="Assistant"
          onThumbs={sent}
        />
        <Message message={message("m3", "Thanks!", true)} author="You" mine sending />
        <Streaming text="" author="Assistant" />
      </Messages>
    </div>
  );
}

function Ended() {
  return (
    <div data-testid="chat" className="flex flex-col gap-6 bg-paper p-4 text-fg">
      <Messages>
        <li>
          <Questions
            request={ASKED}
            answer={{
              answers: [
                { selected: [], other: "The week of 2 November" },
                { selected: ["What shipped", "Metrics"] },
              ],
            }}
            answeredBy="You"
            onAnswer={sent}
          />
        </li>
        <RunFailed
          reason="tool_retries_exhausted"
          error="Tool 'draft_rule' exceeded max retries count of 3"
          onRetry={sent}
        />
      </Messages>
    </div>
  );
}

/** Lay out what to shoot at a width, with the faces loaded and the pointer off it. */
async function shown(width: number, what: React.ReactNode) {
  await page.viewport(width, 1800);
  onTestFinished(() => page.viewport(414, 896));
  const screen = await render(what);
  await Promise.all([
    document.fonts.load('1em "Schibsted Grotesk"'),
    document.fonts.load('600 1em "Schibsted Grotesk"'),
  ]);
  await document.fonts.ready;
  await commands.pointerAway();
  return screen;
}

async function matches(name: string) {
  await expect(page.getByTestId("chat")).toMatchScreenshot(`${name}-${dark ? "dark" : "light"}`, {
    screenshotOptions: { animations: "disabled" },
  });
}

test("a thread: sides, questions, tool calls with one open, and thinking, wide", async () => {
  const screen = await shown(900, <Thread />);
  await screen.getByText("draft_rule").click();
  await matches("chat-wide");
});

test("the same thread, narrow", async () => {
  await shown(390, <Thread />);
  await matches("chat-narrow");
});

test("questions answered, and a failed turn", async () => {
  await shown(900, <Ended />);
  await matches("chat-ended");
});
