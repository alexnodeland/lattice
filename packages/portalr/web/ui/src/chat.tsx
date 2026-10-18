/**
 * The chat: what `client`'s artifactr store holds, rendered, and the commands each part sends,
 * handed to the caller. The components know nothing of the transport (lattice RFC-0002).
 */

import { Field } from "@base-ui/react/field";
import type { Artifactr, ArtifactrV1, Thumb } from "@portalr/client";
import { Bot, ThumbsDown, ThumbsUp } from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Alert } from "./alert";
import type { Values } from "./artifactr-ui";
import { Button } from "./button";
import { cn } from "./cn";
import { CopyButton } from "./copy-button";
import { endedBy, readAskForm } from "./form-schema";
import { Icon } from "./icon";
import { FeatureOff, useFormLock } from "./integrations";
import { Markdown } from "./markdown";
import { SchemaForm } from "./schema-form";
import { type Sent, Unsent, useSending } from "./sending";
import { StatusBadge, type Tone } from "./status-badge";
import { TextField } from "./text-field";
import { TYPE } from "./type";

const card = "flex flex-col gap-2 rounded-lg border border-line bg-surface p-4 text-sm";

/** A button that sends one command, waits while it is in flight, and says why one wasn't done. */
export function CommandButton({
  onSend,
  variant = "secondary",
  children,
}: {
  onSend: () => Sent;
  variant?: "primary" | "secondary";
  children: ReactNode;
}) {
  const { pending, unsent, send } = useSending();
  return (
    <span className="inline-flex flex-col gap-1">
      <Button variant={variant} disabled={pending} onClick={() => send(onSend)}>
        {children}
      </Button>
      <Unsent reason={unsent} />
    </span>
  );
}

/** Give thumbs up or down, and why, if the person says. */
export type GiveThumbs = (up: boolean, comment: string | null) => Sent;

/**
 * Thumbs on something: up or down, then why, if the person wants to say. Each is sent as it is
 * given, and the latest is what shows.
 */
export function Thumbs({ given, onThumbs }: { given: Thumb | null; onThumbs: GiveThumbs }) {
  const { pending, unsent, send } = useSending();
  const [chosen, setChosen] = useState<boolean | null>(null);
  async function thumb(up: boolean) {
    if (await send(() => onThumbs(up, null))) {
      setChosen(up);
    }
  }
  async function explain(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const comment = String(new FormData(event.currentTarget).get("comment")).trim();
    if (chosen !== null && (await send(() => onThumbs(chosen, comment || null)))) {
      setChosen(null);
    }
  }
  return (
    <fieldset aria-label="Feedback" className="m-0 flex min-w-0 flex-col gap-1 border-0 p-0">
      <span className="flex gap-1">
        <Button
          variant="ghost"
          className="border-line px-2 py-1 text-xs"
          aria-pressed={given?.up === true}
          disabled={pending}
          onClick={() => thumb(true)}
        >
          <Icon icon={ThumbsUp} className="size-3.5" />
          Helpful
        </Button>
        <Button
          variant="ghost"
          className="border-line px-2 py-1 text-xs"
          aria-pressed={given?.up === false}
          disabled={pending}
          onClick={() => thumb(false)}
        >
          <Icon icon={ThumbsDown} className="size-3.5" />
          Not helpful
        </Button>
      </span>
      {given?.comment && <p className="text-muted text-xs">You said: {given.comment}</p>}
      {chosen !== null && (
        <form className="flex items-end gap-2" onSubmit={explain}>
          <TextField label="Why? (optional)" name="comment" className="flex-1" />
          <Button type="submit" variant="secondary" disabled={pending}>
            Add
          </Button>
        </form>
      )}
      <Unsent reason={unsent} />
    </fieldset>
  );
}

type MessageProps = {
  message: Artifactr.Message;
  /** How to name who posted it, which names the message too. */
  author: string;
  /** The reader's thumbs on it, as `client`'s `thumbs` reads them. */
  thumbs?: Thumb | null;
  /** Give thumbs; without it, there are none. */
  onThumbs?: GiveThumbs;
};

/**
 * One message, named for who posted it: their name, its Markdown, a way to copy it as the Markdown
 * it was written in, and the reader's thumbs.
 */
export function Message({ message, author, thumbs = null, onThumbs }: MessageProps) {
  const name = useId();
  return (
    <li
      aria-labelledby={name}
      className={cn("flex flex-col gap-1", message.kind === "notice" && "text-muted italic")}
    >
      <span id={name} className="font-semibold text-xs">
        {author}
      </span>
      <Markdown>{message.content}</Markdown>
      <div className="flex flex-wrap items-start gap-1">
        <CopyButton text={message.content} what="as Markdown" />
        {onThumbs && <Thumbs given={thumbs} onThumbs={onThumbs} />}
      </div>
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
    <form
      className="flex flex-col gap-1 rounded-lg border border-edge bg-surface p-1 outline-offset-2 has-[textarea:focus-visible]:outline-2 has-[textarea:focus-visible]:outline-focus"
      onSubmit={submit}
    >
      <Field.Root className="flex flex-col" disabled={disabled}>
        <Field.Label className="sr-only">Message</Field.Label>
        <Field.Control
          render={<textarea rows={2} />}
          value={text}
          placeholder="Write to the assistant"
          onValueChange={(value) => setText(String(value))}
          onKeyDown={key}
          className="min-h-14 resize-none bg-transparent px-2.5 py-2 text-base text-fg outline-none placeholder:text-muted data-disabled:cursor-not-allowed data-disabled:text-muted"
        />
      </Field.Root>
      <div className="flex items-center justify-between gap-2 px-2.5 pb-1">
        <span className="text-muted text-xs max-sm:hidden">
          Enter sends, Shift+Enter starts a new line
        </span>
        <Button type="submit" className="ml-auto" disabled={disabled || pending || !text.trim()}>
          Send
        </Button>
      </div>
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

/** The deferred tool that asks a form, whose answer is the form's values (lattice RFC-0005). */
export const ASK_FORM = "ask_form";

type Answer = { approved: boolean } | { answer: string } | { answer: Values };

/**
 * A form the agent asks through `ask_form`, its fields from the request's arguments, answered
 * once with its values. Once anyone has answered it, it says who, in place of its fields ("You",
 * or a name, as the thread names people), until its run ends; and if the reader's answer comes
 * after another's, it says it was answered already.
 */
function FormRequest({
  request,
  answeredBy,
  focus,
  onAnswer,
}: {
  request: ArtifactrV1.DeferredRequest;
  answeredBy: string | null | undefined;
  focus: boolean;
  onAnswer: (values: Values) => Sent;
}) {
  const asked = useMemo(() => readAskForm(request.args), [request.args]);
  const [late, setLate] = useState(false);
  // Off in the workspace, or refused as off by the server: the form stays, and can't be sent.
  const { off, refused: refusedAsOff } = useFormLock();
  async function answer(values: Values) {
    const settled = await onAnswer(values);
    const ended = settled.outcome === "refused" ? endedBy(settled.result?.rejection) : null;
    if (ended?.reason === "answered") {
      setLate(true);
    } else if (ended?.reason === "off") {
      refusedAsOff(ended.integration);
    }
    return settled;
  }
  const ended =
    late || answeredBy !== undefined ? (
      <Alert>
        {late ? "Already answered" : "Answered"}
        {answeredBy && `: ${answeredBy} ${late ? "answered it first" : "answered it"}`}.
      </Alert>
    ) : undefined;
  return (
    <div className={cn(card, "gap-3", ended === undefined && off === null && "border-accent")}>
      <p className={cn(TYPE.note, "inline-flex items-center gap-1.5")}>
        <Icon icon={Bot} className="size-3.5" />
        The agent asks
      </p>
      {asked === null ? (
        <Alert tone="warn">
          This form can't be shown here: its fields aren't ones portalr can show.
        </Alert>
      ) : (
        <SchemaForm
          {...(asked.title !== "" && { title: asked.title })}
          schema={asked.schema}
          ui={asked.ui}
          onSubmit={answer}
          ended={ended}
          {...(off !== null && { locked: <FeatureOff integration={off} /> })}
          autoFocus={focus && answeredBy === undefined}
        />
      )}
    </div>
  );
}

/**
 * What a paused run waits on: a call to approve or deny, a question to answer, or a form to fill
 * in. It takes the focus when it appears, unless `focus` says another should, and answers once,
 * with `answer_deferred`. A form, asked through `ask_form`, stays once it is answered, until its
 * run ends, and says by whom: `answeredBy`, or null where who isn't known.
 */
export function Request({
  request,
  onAnswer,
  answeredBy,
  focus = true,
}: {
  request: ArtifactrV1.DeferredRequest;
  onAnswer: (answer: Answer) => Sent;
  answeredBy?: string | null;
  /** Take the focus as it appears: the newest of a run's forms does, and an answered one never. */
  focus?: boolean;
}) {
  return request.tool_name === ASK_FORM ? (
    <FormRequest
      request={request}
      answeredBy={answeredBy}
      focus={focus}
      onAnswer={(values) => onAnswer({ answer: values })}
    />
  ) : (
    <Question request={request} focus={focus} onAnswer={onAnswer} />
  );
}

/** A call to approve or deny, or a question to answer in a line. */
function Question({
  request,
  focus,
  onAnswer,
}: {
  request: ArtifactrV1.DeferredRequest;
  focus: boolean;
  onAnswer: (answer: Answer) => Sent;
}) {
  const [answered, setAnswered] = useState(false);
  const { pending, unsent, send } = useSending();
  const first = useRef<HTMLButtonElement & HTMLInputElement>(null);
  useEffect(() => {
    if (focus) {
      first.current?.focus();
    }
  }, [focus]);
  async function answer(given: Answer) {
    setAnswered(await send(() => onAnswer(given)));
  }
  const closed = answered || pending;
  if (request.kind === "approval") {
    const args = Object.keys(request.args ?? {}).length > 0;
    return (
      <section className={cn(card, "border-accent")} aria-label={`Approve ${request.tool_name}?`}>
        <p>
          The agent wants to run <code className="font-mono">{request.tool_name}</code>.
        </p>
        {args && (
          <pre className="overflow-x-auto rounded-md border border-line bg-paper p-3 font-mono text-xs">
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

/** The artifact a proposal would change, if it names one: a new one's is chosen when accepted. */
export function proposedOn(proposal: Artifactr.Proposal): string | null {
  const { change } = proposal;
  return change !== null && "artifact_id" in change ? (change.artifact_id ?? null) : null;
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

/**
 * A proposed change, with accept and reject while it is open, and what its caller adds. Where its
 * caller knows it can't be accepted, such as one made against a version of a file since replaced,
 * Accept is disabled and the reason is said beside it; it can still be rejected.
 */
export function ProposalCard({
  proposal,
  onRespond,
  blocked = null,
  children,
}: {
  proposal: Artifactr.Proposal;
  onRespond?: (decision: "accept" | "reject") => Sent;
  /** Why it can't be accepted, or null where it can. */
  blocked?: string | null;
  /** More about it, such as a link to the artifact it would change. */
  children?: ReactNode;
}) {
  const what = proposal.change ? describe(proposal.change) : "A change";
  const { pending, unsent, send } = useSending();
  const why = useId();
  return (
    <section className={card} aria-label={`Proposal: ${what}`}>
      <p className="font-semibold">{what}</p>
      {proposal.rationale && <p className="text-muted">{proposal.rationale}</p>}
      {children}
      {proposal.status === "open" && blocked !== null && (
        <p id={why} className="text-muted text-sm">
          {blocked}
        </p>
      )}
      {proposal.status === "open" ? (
        onRespond && (
          <span className="flex gap-2">
            <Button
              disabled={pending || blocked !== null}
              focusableWhenDisabled={blocked !== null}
              aria-describedby={blocked === null ? undefined : why}
              onClick={() => send(() => onRespond("accept"))}
            >
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
        <StatusBadge
          tone={proposal.status === "accept" ? "done" : "stopped"}
          className="self-start"
        >
          {proposal.status === "accept" ? "Accepted" : "Rejected"}
        </StatusBadge>
      )}
      <Unsent reason={unsent} />
    </section>
  );
}

/** How a run is going, in words and a shape: one wording wherever a run is shown. */
const RUN_STATUS: Record<Artifactr.Run["status"], readonly [Tone, string]> = {
  running: ["working", "Working"],
  paused: ["waiting", "Waiting for you"],
  completed: ["done", "Done"],
  failed: ["failed", "Failed"],
  stopped: ["stopped", "Stopped"],
};

/** How a run is going, announced as it changes. */
export function RunStatus({ status }: { status: Artifactr.Run["status"] }) {
  const [tone, words] = RUN_STATUS[status];
  return (
    <StatusBadge tone={tone} live className="self-start">
      {words}
    </StatusBadge>
  );
}
