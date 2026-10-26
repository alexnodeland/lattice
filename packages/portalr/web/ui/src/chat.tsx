/**
 * The chat: what `client`'s artifactr store holds, rendered, and the commands each part sends,
 * handed to the caller. The components know nothing of the transport (lattice RFC-0002).
 */

import { Field } from "@base-ui/react/field";
import type { Artifactr, ArtifactrV1, Thumb } from "@portalr/client";
import { Bot, FileText, Maximize2, Minimize2, ThumbsDown, ThumbsUp } from "lucide-react";
import {
  type FormEvent,
  type KeyboardEvent,
  type ReactElement,
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
import { useFullView } from "./full-view";
import { Icon } from "./icon";
import { IconButton } from "./icon-button";
import { FeatureOff, useFormLock } from "./integrations";
import { Markdown } from "./markdown";
import { Questions, type QuestionsAnswer } from "./questions";
import { SchemaForm } from "./schema-form";
import { type Sent, Unsent, useSending } from "./sending";
import { FOLDED_LINES, SourceView } from "./source-view";
import { StatusBadge, type Tone } from "./status-badge";
import { TextField } from "./text-field";
import { TextLink } from "./text-link";
import { TYPE } from "./type";

const card =
  "flex flex-col gap-2 rounded-(--card-radius) border border-line bg-surface p-(--card-pad) text-sm";

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
      <Button variant={variant} pending={pending} onClick={() => send(onSend)}>
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
        <IconButton
          label="Helpful"
          icon={ThumbsUp}
          aria-pressed={given?.up === true}
          disabled={pending}
          focusableWhenDisabled
          onClick={() => thumb(true)}
        />
        <IconButton
          label="Not helpful"
          icon={ThumbsDown}
          aria-pressed={given?.up === false}
          disabled={pending}
          focusableWhenDisabled
          onClick={() => thumb(false)}
        />
      </span>
      {given?.comment && <p className="text-muted text-xs">You said: {given.comment}</p>}
      {chosen !== null && (
        <form className="flex items-end gap-2" onSubmit={explain}>
          <TextField label="Why? (optional)" name="comment" className="flex-1" />
          <Button type="submit" variant="secondary" pending={pending}>
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
  /** Whether the reader posted it, which sets it at the end of the line, as theirs. */
  mine?: boolean;
  /** Whether it is on its way: shown as the reader wrote it until the thread has it. */
  sending?: boolean;
  /** Send it again, under its id, where its answer never came: it says so, with a button. */
  onSendAgain?: () => Sent;
  /** The reader's thumbs on it, as `client`'s `thumbs` reads them. */
  thumbs?: Thumb | null;
  /** Give thumbs; without it, there are none. */
  onThumbs?: GiveThumbs;
};

/** A message's bubble: the reader's at the end of the line, everyone else's at its start. */
const bubble = (mine: boolean) =>
  cn(
    "min-w-0 max-w-full rounded-(--bubble-radius) border px-(--bubble-pad-x) py-(--bubble-pad-y)",
    mine
      ? "rounded-se-(--bubble-tail-radius) border-line bg-wash"
      : "rounded-ss-(--bubble-tail-radius) border-line bg-surface",
  );

/**
 * One message, named for who posted it: their name, its Markdown in a bubble, a way to copy it as
 * the Markdown it was written in, and the reader's thumbs. The reader's own are at the end of the
 * line, the agent's and others' at its start, in either direction of writing. A notice is set
 * apart, without a bubble.
 */
export function Message({
  message,
  author,
  mine = false,
  sending = false,
  onSendAgain,
  thumbs = null,
  onThumbs,
}: MessageProps) {
  const name = useId();
  const notice = message.kind === "notice";
  return (
    <li
      aria-labelledby={name}
      aria-busy={sending || undefined}
      className={cn(
        "flex max-w-[min(100%,var(--bubble-max-width))] flex-col gap-1",
        mine ? "items-end self-end" : "items-start self-start",
        notice && "text-muted italic",
      )}
    >
      <span id={name} className="font-semibold text-xs">
        {author}
      </span>
      <div className={notice ? "min-w-0 max-w-full" : bubble(mine)}>
        <Markdown>{message.content}</Markdown>
      </div>
      <div className="flex min-h-7 flex-wrap items-start gap-1">
        {sending && onSendAgain ? (
          <span className="flex items-center gap-2">
            <span className={TYPE.note}>It may not have been sent.</span>
            <CommandButton onSend={onSendAgain}>Send again</CommandButton>
          </span>
        ) : sending ? (
          <span className={TYPE.note}>Sending…</span>
        ) : (
          <>
            <CopyButton text={message.content} what="as Markdown" />
            {onThumbs && <Thumbs given={thumbs} onThumbs={onThumbs} />}
          </>
        )}
      </div>
    </li>
  );
}

/**
 * What a run is streaming, as it arrives, in the bubble its message will have, so nothing moves
 * when the message replaces it. Before its first words, it says the agent is thinking.
 */
export function Streaming({ text, author }: { text: string; author: string }) {
  return (
    <li
      className="flex max-w-[min(100%,var(--bubble-max-width))] flex-col items-start gap-1 self-start"
      aria-busy="true"
      aria-label={text ? `${author} is writing` : `${author} is thinking`}
    >
      <span className="font-semibold text-xs">{author}</span>
      <div className={bubble(false)}>
        {text ? <Markdown streaming>{text}</Markdown> : <Thinking />}
      </div>
      <div aria-hidden="true" className="min-h-7" />
    </li>
  );
}

/** Three dots that pulse in turn while the agent thinks, and stay still where motion is reduced. */
function Thinking() {
  return (
    <span className="flex h-6 items-center gap-1 text-muted">
      {/* Each dot a beat behind the last: a delay, not a duration, so reduced motion's pause holds. */}
      {[0, 150, 300].map((delay) => (
        <span
          key={delay}
          style={{ animationDelay: `${delay}ms` }}
          className="size-1.5 rounded-full bg-current [animation-play-state:var(--motion-loop)] motion-safe:animate-pulse"
        />
      ))}
      <span className="sr-only">Thinking</span>
    </span>
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

/**
 * An artifact shown in the thread it was made in, where it was made, as its kind's renderer draws
 * it, with a way to its own page (`open`): one per artifact, at its latest version. With `kind`,
 * it is named above what it draws, and has a full view of its own, which fills the window as a
 * modal dialog and keeps what is drawn as it is, a form's answers included; an app, which names
 * itself and has its own, takes neither (portalr ADR-0055).
 */
export function InlineArtifact({
  name,
  kind,
  open,
  actions,
  children,
}: {
  /** What it is called, which names it in the log. */
  name: string;
  /** Icon buttons of its own, such as a file's download, set in its header before its page's. */
  actions?: ReactNode;
  /** What kind of thing it is, as people say it, such as "Note" or "Word document". */
  kind?: string;
  /**
   * The link to its own page, where it has its history, such as the router's: drawn as the card's
   * "Open its page", in its header with its kind, or under it without (portalr ADR-0061).
   */
  open: ReactElement | null;
  children: ReactNode;
}) {
  const { full, setFull, box, back } = useFullView();
  if (kind === undefined) {
    return (
      <li aria-label={name} className={card}>
        {children}
        {open && (
          <span className="self-start text-xs">
            <TextLink render={open}>Open its page</TextLink>
          </span>
        )}
      </li>
    );
  }
  return (
    <li aria-label={name} className={card}>
      <div
        ref={box}
        className={cn(
          "flex min-w-0 flex-col gap-3",
          full && "fixed inset-0 z-50 overflow-y-auto overscroll-contain bg-paper p-4 sm:p-6",
        )}
        {...(full && { role: "dialog", "aria-modal": true, "aria-label": name })}
      >
        <div className="flex items-start justify-between gap-3">
          <p className="flex min-w-0 flex-col gap-0.5">
            <span className={TYPE.note}>{kind}</span>
            <span className={cn(TYPE.label, "break-words")}>{name}</span>
          </p>
          <span className="flex shrink-0 items-center gap-1">
            {/* In the full view, the way back alone (portalr ADR-0061). */}
            {!full && actions}
            {open && !full && <IconButton label="Open its page" icon={FileText} render={open} />}
            <IconButton
              ref={back}
              escapeThrough={full}
              label={full ? "Back to the page" : "Full view"}
              icon={full ? Minimize2 : Maximize2}
              onClick={() => setFull(!full)}
            />
          </span>
        </div>
        <div className={cn("min-w-0", full && "mx-auto w-full max-w-5xl")}>{children}</div>
      </div>
    </li>
  );
}

/**
 * Write a message: Enter sends it, Shift+Enter starts a new line, and composing text waits. It
 * grows with its lines, to a height, then scrolls (portalr ADR-0079). It clears as it sends, as
 * the thread shows the message at once; one refused comes back.
 */
export function Composer({
  onSend,
  disabled = false,
}: {
  /**
   * Post the message; the text is cleared as it is sent, and comes back if the server refused
   * it. One whose answer never came may have been posted: the thread offers to send it again.
   */
  onSend: (text: string) => Sent;
  disabled?: boolean;
}) {
  const [text, setText] = useState("");
  const { pending, unsent, send: sending } = useSending();
  // A draft not yet sent: leaving the page, or reloading it, asks first.
  const drafted = text.trim() !== "";
  useEffect(() => {
    if (!drafted) {
      return;
    }
    const ask = (event: BeforeUnloadEvent) => event.preventDefault();
    addEventListener("beforeunload", ask);
    return () => removeEventListener("beforeunload", ask);
  }, [drafted]);
  async function send() {
    const message = text.trim();
    if (message && !pending) {
      setText("");
      let refused = false;
      const told = (settled: { outcome: string }) => {
        refused = settled.outcome === "refused";
        return false; // the composer says why, whatever it was
      };
      if (!(await sending(() => onSend(message), told)) && refused) {
        setText((written) => written || message); // back, unless something new was written
      }
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
      className="flex flex-col gap-1 rounded-(--composer-radius) border border-edge bg-surface p-(--composer-pad) outline-offset-(--focus-offset) has-[textarea:focus-visible]:outline-(length:--focus-width) has-[textarea:focus-visible]:outline-focus"
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
          className="max-h-64 min-h-14 field-sizing-content resize-none bg-transparent px-2.5 py-2 text-base text-fg outline-none placeholder:text-muted data-disabled:cursor-not-allowed data-disabled:text-muted"
        />
      </Field.Root>
      <div className="flex items-center justify-between gap-2 px-2.5 pb-1">
        <span className="text-muted text-xs max-sm:hidden">
          Enter sends, Shift+Enter starts a new line
        </span>
        <Button
          type="submit"
          className="ml-auto"
          disabled={disabled || !text.trim()}
          pending={pending}
        >
          Send
        </Button>
      </div>
      <Unsent reason={unsent} />
    </form>
  );
}

/** The deferred tool that asks a form, whose answer is the form's values (lattice RFC-0005). */
export const ASK_FORM = "ask_form";

/** The deferred tool that asks questions with options, answered per question (artifactr ADR-0083). */
export const ASK_USER = "ask_user";

type Answer =
  | { approved: boolean }
  | { answer: string }
  | { answer: Values }
  | { answer: QuestionsAnswer };

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
 * What a paused run waits on: a call to approve or deny, questions to answer (`ask_user`'s
 * options, or another tool's in a line), or a form to fill in. It takes the focus when it appears, unless `focus` says another should, and answers once,
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
  switch (request.tool_name) {
    case ASK_FORM:
      return (
        <FormRequest
          request={request}
          answeredBy={answeredBy}
          focus={focus}
          onAnswer={(values) => onAnswer({ answer: values })}
        />
      );
    case ASK_USER:
      return (
        <Questions request={request} focus={focus} onAnswer={(answer) => onAnswer({ answer })} />
      );
    default:
      return <Question request={request} focus={focus} onAnswer={onAnswer} />;
  }
}

/** A call to approve or deny, or another tool's question to answer in a line. */
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
        <Review review={request.review ?? {}} />
        {args && (
          <pre className="overflow-x-auto rounded-(--code-block-radius) border border-line bg-paper p-(--code-panel-pad) font-mono text-xs">
            {unhidden(JSON.stringify(request.args, null, 2))}
          </pre>
        )}
        <span className="flex gap-2">
          <Button
            ref={first}
            disabled={answered}
            pending={pending}
            onClick={() => void answer({ approved: true })}
          >
            Approve
          </Button>
          <Button
            variant="secondary"
            disabled={answered}
            pending={pending}
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
      <Button type="submit" disabled={answered} pending={pending}>
        Answer
      </Button>
      <Unsent reason={unsent} />
    </form>
  );
}

/**
 * What a connected app's call does, beside its arguments (artifactr ADR-0085): that it runs code,
 * or fetches, in the operator's own app, with their privileges, and from where; the code itself,
 * whole, to read and copy; what a scan found in it, which is advisory: the person reading is the
 * gate; and how many of the workspace's calls an hour this one is.
 */
function Review({ review }: { review: Record<string, unknown> }) {
  const { app, risk, runs, reaches, holds, hour, code, findings } = review;
  if (typeof app !== "string" || typeof runs !== "string") {
    return null;
  }
  const found = Array.isArray(findings) ? findings.filter((f) => typeof f === "string") : [];
  const lines = typeof code === "string" ? code.split("\n").length : 0;
  return (
    <div className="flex flex-col gap-2">
      <StatusBadge tone="retrying" className="self-start">
        {risk === "network"
          ? `Downloads from the internet into your ${app}`
          : `Runs code in your ${app}`}
      </StatusBadge>
      <p>{runs}</p>
      {typeof reaches === "string" && <p>{`It reaches ${reaches}.`}</p>}
      {typeof holds === "string" && <p>{holds}</p>}
      {typeof hour === "string" && <p>{hour}</p>}
      {typeof code === "string" && (
        <>
          {lines > FOLDED_LINES && (
            <p>{`It is ${lines} lines long: show all of it, and read to the end.`}</p>
          )}
          <SourceView code={unhidden(code)} language="python" name="code" />
          {found.length > 0 ? (
            <div>
              <p>A quick scan found these. It can't find everything: read the code.</p>
              <ul className="list-disc ps-5">
                {found.map((finding) => (
                  <li key={finding}>{finding}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p>A quick scan found nothing; it can't find everything.</p>
          )}
        </>
      )}
    </div>
  );
}

/** The ranges of characters a reader wouldn't see, as artifactr's scan finds them, kept in step
 * with its `HIDDEN`: controls but tabs and newlines, separators, soft hyphens, zero-width,
 * direction-changing and tag characters, variation selectors, and lone surrogates. */
const HIDDEN: readonly (readonly [number, number])[] = [
  [0x00, 0x08],
  [0x0b, 0x0c],
  [0x0e, 0x1f],
  [0x7f, 0x9f],
  [0xad, 0xad],
  [0x61c, 0x61c],
  [0x180e, 0x180e],
  [0x200b, 0x200f],
  [0x2028, 0x202e],
  [0x2060, 0x2064],
  [0x2066, 0x2069],
  [0xfe00, 0xfe0f],
  [0xfeff, 0xfeff],
  [0xd800, 0xdfff],
  [0xe0000, 0xe007f],
  [0xe0100, 0xe01ef],
];

/** Code with each character a reader wouldn't see shown as its code point, so what is read is
 * what runs; Copy copies it so too. */
export function unhidden(code: string): string {
  let shown = "";
  for (const c of code) {
    const point = c.codePointAt(0) ?? 0;
    const hidden = HIDDEN.some(([low, high]) => point >= low && point <= high);
    shown += hidden ? `\u27e6U+${point.toString(16).toUpperCase().padStart(4, "0")}\u27e7` : c;
  }
  return shown;
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
              disabled={blocked !== null}
              focusableWhenDisabled={blocked !== null}
              pending={pending}
              aria-describedby={blocked === null ? undefined : why}
              onClick={() => send(() => onRespond("accept"))}
            >
              Accept
            </Button>
            <Button
              variant="secondary"
              pending={pending}
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
