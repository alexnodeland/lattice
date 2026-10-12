/**
 * The chat: what `client`'s artifactr store holds, rendered, and the commands each part sends,
 * handed to the caller. The components know nothing of the transport (lattice RFC-0002).
 */

import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import { type FormEvent, type KeyboardEvent, useState } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { Markdown } from "./markdown";
import { TextField } from "./text-field";

const card = "flex flex-col gap-2 rounded-md border border-line bg-surface p-3 text-sm";

/** Whether a message's latest thumbs from this person was up, down, or not given. */
function thumbs(message: Artifactr.Message, me: string): boolean | null {
  const mine = message.feedback.filter(
    (given) => given.type === "thumbs" && "id" in given.actor && given.actor.id === me,
  );
  const up = mine.at(-1)?.value.up;
  return typeof up === "boolean" ? up : null;
}

type MessageProps = {
  message: Artifactr.Message;
  /** How to name who posted it. */
  author: string;
  /** The signed-in person's id, whose thumbs the buttons show. */
  me: string;
  /** Give thumbs up or down; without it, there are no buttons. */
  onThumbs?: (up: boolean) => void;
};

/** One message: who posted it, its Markdown, and thumbs for the person reading it. */
export function Message({ message, author, me, onThumbs }: MessageProps) {
  const given = thumbs(message, me);
  return (
    <li
      className={cn("flex flex-col gap-1", message.kind === "notice" && "text-muted italic")}
      aria-label={`${author}: ${message.content}`}
    >
      <span className="font-semibold text-xs">{author}</span>
      <Markdown>{message.content}</Markdown>
      {onThumbs && (
        <span className="flex gap-1">
          <Button variant="secondary" aria-pressed={given === true} onClick={() => onThumbs(true)}>
            Helpful
          </Button>
          <Button
            variant="secondary"
            aria-pressed={given === false}
            onClick={() => onThumbs(false)}
          >
            Not helpful
          </Button>
        </span>
      )}
    </li>
  );
}

/** What a run is streaming, as it arrives. */
export function Streaming({ text, author }: { text: string; author: string }) {
  return (
    <li className="flex flex-col gap-1" aria-busy="true" aria-label={`${author} is writing`}>
      <span className="font-semibold text-xs">{author}</span>
      <Markdown streaming>{text}</Markdown>
    </li>
  );
}

/** A thread's messages, oldest first, and what is streaming after them. */
export function Messages({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <ol aria-label="Messages" className={cn("flex flex-col gap-4", className)}>
      {children}
    </ol>
  );
}

/** Write a message: Enter sends it, Shift+Enter starts a new line. */
export function Composer({
  onSend,
  disabled = false,
}: {
  onSend: (text: string) => void;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  function send() {
    const message = text.trim();
    if (message) {
      onSend(message);
      setText("");
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    send();
  }
  function key(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      send();
    }
  }
  return (
    <form className="flex items-end gap-2" onSubmit={submit}>
      <label className="flex flex-1 flex-col gap-1 font-semibold text-sm">
        Message
        <textarea
          className="min-h-16 rounded-md border border-line bg-surface px-3 py-1.5 font-normal text-fg text-sm outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus"
          value={text}
          disabled={disabled}
          onChange={(event) => setText(event.target.value)}
          onKeyDown={key}
        />
      </label>
      <Button type="submit" disabled={disabled || !text.trim()}>
        Send
      </Button>
    </form>
  );
}

/** A tool the run called, and how it returned. */
export function ToolCall({ tool }: { tool: Artifactr.Tool }) {
  return (
    <li className={cn(card, "flex-row items-center justify-between")}>
      <code className="font-mono">{tool.name}</code>
      <span className="text-muted">{tool.status === "called" ? "running" : tool.status}</span>
    </li>
  );
}

/**
 * What a paused run waits on: a call to approve or deny, or a question to answer. Answering one
 * sends `answer_deferred`.
 */
export function Request({
  request,
  onAnswer,
}: {
  request: ArtifactrV1.DeferredRequest;
  onAnswer: (answer: { approved: boolean } | { answer: string }) => void;
}) {
  const args = Object.keys(request.args ?? {}).length > 0;
  if (request.kind === "approval") {
    return (
      <section className={card} aria-label={`Approve ${request.tool_name}?`}>
        <p>
          The agent wants to run <code className="font-mono">{request.tool_name}</code>.
        </p>
        {args && (
          <pre className="overflow-x-auto font-mono text-xs">
            {JSON.stringify(request.args, null, 2)}
          </pre>
        )}
        <span className="flex gap-2">
          <Button onClick={() => onAnswer({ approved: true })}>Approve</Button>
          <Button variant="secondary" onClick={() => onAnswer({ approved: false })}>
            Deny
          </Button>
        </span>
      </section>
    );
  }
  return <Question request={request} onAnswer={(answer) => onAnswer({ answer })} />;
}

function Question({
  request,
  onAnswer,
}: {
  request: ArtifactrV1.DeferredRequest;
  onAnswer: (answer: string) => void;
}) {
  const asked = request.args?.question;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onAnswer(String(new FormData(event.currentTarget).get("answer")));
  }
  return (
    <form className={card} aria-label="The agent asks" onSubmit={submit}>
      <p>{typeof asked === "string" ? asked : `The agent asks, through ${request.tool_name}.`}</p>
      <TextField label="Answer" name="answer" required />
      <Button type="submit">Answer</Button>
    </form>
  );
}

/** What a change would do, in words. */
function describe(change: NonNullable<Artifactr.Proposal["change"]>): string {
  switch (change.type) {
    case "create_artifact":
      return `Create a ${change.kind}${change.artifact_id ? `, ${change.artifact_id}` : ""}`;
    case "edit_artifact":
      return change.summary ?? `Edit ${change.artifact_id}`;
    case "archive_artifact":
      return `Archive ${change.artifact_id}`;
    default:
      return change satisfies never;
  }
}

/** A proposed change, with accept and reject while it is open. */
export function ProposalCard({
  proposal,
  onRespond,
}: {
  proposal: Artifactr.Proposal;
  onRespond?: (decision: "accept" | "reject") => void;
}) {
  const what = proposal.change ? describe(proposal.change) : "A change";
  return (
    <section className={card} aria-label={`Proposal: ${what}`}>
      <p className="font-semibold">{what}</p>
      {proposal.rationale && <p className="text-muted">{proposal.rationale}</p>}
      {proposal.status === "open" ? (
        onRespond && (
          <span className="flex gap-2">
            <Button onClick={() => onRespond("accept")}>Accept</Button>
            <Button variant="secondary" onClick={() => onRespond("reject")}>
              Reject
            </Button>
          </span>
        )
      ) : (
        <p>{proposal.status === "accept" ? "Accepted" : "Rejected"}</p>
      )}
    </section>
  );
}

const STATUS: Record<string, string> = {
  running: "Working",
  paused: "Waiting for you",
  completed: "Done",
  failed: "Failed",
  stopped: "Stopped",
};

/** How a run is going, announced as it changes. */
export function RunStatus({ status }: { status: string }) {
  return (
    <p role="status" className="text-muted text-xs">
      {STATUS[status] ?? status}
    </p>
  );
}
