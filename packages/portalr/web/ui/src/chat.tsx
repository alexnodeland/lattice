/**
 * The chat: what `client`'s artifactr store holds, rendered, and the commands each part sends,
 * handed to the caller. The components know nothing of the transport (lattice RFC-0002).
 */

import type { Artifactr, ArtifactrV1 } from "@portalr/client";
import {
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { Markdown } from "./markdown";
import { TextField } from "./text-field";

const card = "flex flex-col gap-2 rounded-md border border-line bg-surface p-3 text-sm";

/** How a command a part handed its caller ended, as `client`'s stream settles it. */
export type Sent = Promise<{ readonly outcome: "done" | "refused" | "closed" }>;

const UNSENT = {
  refused: "That wasn't done: the server refused it.",
  closed: "That wasn't sent: the connection closed.",
} as const;

/** A command in flight: whether it is, and why the last one wasn't done. */
function useSending() {
  const [pending, setPending] = useState(false);
  const [unsent, setUnsent] = useState<string | null>(null);
  async function send(command: () => Sent): Promise<boolean> {
    setPending(true);
    setUnsent(null);
    const { outcome } = await command();
    setPending(false);
    if (outcome !== "done") {
      setUnsent(UNSENT[outcome]);
    }
    return outcome === "done";
  }
  return { pending, unsent, send };
}

/** Why a command wasn't done, announced. */
function Unsent({ reason }: { reason: string | null }) {
  return reason && <p role="alert">{reason}</p>;
}

type MessageProps = {
  message: Artifactr.Message;
  /** How to name who posted it, which names the message too. */
  author: string;
  /** The reader's thumbs on it, as `client`'s `thumbs` reads them: up, down, or none. */
  thumbs?: boolean | null;
  /** Give thumbs up or down; without it, there are no buttons. */
  onThumbs?: (up: boolean) => Sent;
};

/** One message, named for who posted it: their name, its Markdown, and the reader's thumbs. */
export function Message({ message, author, thumbs = null, onThumbs }: MessageProps) {
  const name = useId();
  const { pending, unsent, send } = useSending();
  return (
    <li
      aria-labelledby={name}
      className={cn("flex flex-col gap-1", message.kind === "notice" && "text-muted italic")}
    >
      <span id={name} className="font-semibold text-xs">
        {author}
      </span>
      <Markdown>{message.content}</Markdown>
      {onThumbs && (
        <span className="flex gap-1">
          <Button
            variant="secondary"
            aria-pressed={thumbs === true}
            disabled={pending}
            onClick={() => send(() => onThumbs(true))}
          >
            Helpful
          </Button>
          <Button
            variant="secondary"
            aria-pressed={thumbs === false}
            disabled={pending}
            onClick={() => send(() => onThumbs(false))}
          >
            Not helpful
          </Button>
        </span>
      )}
      <Unsent reason={unsent} />
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

/** A thread's messages, oldest first, and what is streaming after them, announced as they come. */
export function Messages({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div role="log" aria-label="Messages">
      <ol className={cn("flex flex-col gap-4", className)}>{children}</ol>
    </div>
  );
}

/** Write a message: Enter sends it, Shift+Enter starts a new line, and composing text waits. */
export function Composer({
  onSend,
  disabled = false,
}: {
  /** Post the message; the text stays until the post is done. */
  onSend: (text: string) => Sent;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const { pending, unsent, send: sending } = useSending();
  async function send() {
    const message = text.trim();
    if (message && !pending && (await sending(() => onSend(message)))) {
      setText("");
    }
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void send();
  }
  function key(event: KeyboardEvent<HTMLElement>) {
    // An input method's Enter chooses its candidate; it doesn't send.
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void send();
    }
  }
  return (
    <form className="flex flex-wrap items-end gap-2" onSubmit={submit}>
      <TextField
        label="Message"
        className="flex-1"
        render={<textarea className="min-h-16" />}
        value={text}
        disabled={disabled}
        onValueChange={(value) => setText(String(value))}
        onKeyDown={key}
      />
      <Button type="submit" disabled={disabled || pending || !text.trim()}>
        Send
      </Button>
      <Unsent reason={unsent} />
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

type Answer = { approved: boolean } | { answer: string };

/**
 * What a paused run waits on: a call to approve or deny, or a question to answer. It takes the
 * focus when it appears, and answers once, with `answer_deferred`.
 */
export function Request({
  request,
  onAnswer,
}: {
  request: ArtifactrV1.DeferredRequest;
  onAnswer: (answer: Answer) => Sent;
}) {
  const [answered, setAnswered] = useState(false);
  const { pending, unsent, send } = useSending();
  const first = useRef<HTMLButtonElement & HTMLInputElement>(null);
  useEffect(() => {
    first.current?.focus();
  }, []);
  async function answer(given: Answer) {
    setAnswered(await send(() => onAnswer(given)));
  }
  const closed = answered || pending;
  if (request.kind === "approval") {
    const args = Object.keys(request.args ?? {}).length > 0;
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
          <Button ref={first} disabled={closed} onClick={() => void answer({ approved: true })}>
            Approve
          </Button>
          <Button
            variant="secondary"
            disabled={closed}
            onClick={() => void answer({ approved: false })}
          >
            Deny
          </Button>
        </span>
        <Unsent reason={unsent} />
      </section>
    );
  }
  const asked = request.args?.question;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void answer({ answer: String(new FormData(event.currentTarget).get("answer")) });
  }
  return (
    <form className={card} aria-label="The agent asks" onSubmit={submit}>
      <p>{typeof asked === "string" ? asked : `The agent asks, through ${request.tool_name}.`}</p>
      <TextField label="Answer" name="answer" ref={first} disabled={closed} required />
      <Button type="submit" disabled={closed}>
        Answer
      </Button>
      <Unsent reason={unsent} />
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
  onRespond?: (decision: "accept" | "reject") => Sent;
}) {
  const what = proposal.change ? describe(proposal.change) : "A change";
  const { pending, unsent, send } = useSending();
  return (
    <section className={card} aria-label={`Proposal: ${what}`}>
      <p className="font-semibold">{what}</p>
      {proposal.rationale && <p className="text-muted">{proposal.rationale}</p>}
      {proposal.status === "open" ? (
        onRespond && (
          <span className="flex gap-2">
            <Button disabled={pending} onClick={() => send(() => onRespond("accept"))}>
              Accept
            </Button>
            <Button
              variant="secondary"
              disabled={pending}
              onClick={() => send(() => onRespond("reject"))}
            >
              Reject
            </Button>
          </span>
        )
      ) : (
        <p>{proposal.status === "accept" ? "Accepted" : "Rejected"}</p>
      )}
      <Unsent reason={unsent} />
    </section>
  );
}

const STATUS: Record<Artifactr.Run["status"], string> = {
  running: "Working",
  paused: "Waiting for you",
  completed: "Done",
  failed: "Failed",
  stopped: "Stopped",
};

/** How a run is going, announced as it changes. */
export function RunStatus({ status }: { status: Artifactr.Run["status"] }) {
  return (
    <p role="status" className="text-muted text-xs">
      {STATUS[status]}
    </p>
  );
}
