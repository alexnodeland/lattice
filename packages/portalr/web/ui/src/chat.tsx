/**
 * The chat: what `client`'s artifactr store holds, rendered, and the commands each part sends,
 * handed to the caller. The components know nothing of the transport (lattice RFC-0002).
 */

import { Field } from "@base-ui/react/field";
import type { Artifactr, ArtifactrV1, Thumb } from "@portalr/client";
import {
  type DragEvent,
  type FormEvent,
  type KeyboardEvent,
  type MouseEvent,
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
import { Button, ButtonLink } from "./button";
import { cn } from "./cn";
import { CopyButton } from "./copy-button";
import { Disclosure } from "./disclosure";
import { endedBy, readAskForm } from "./form-schema";
import { useFullView } from "./full-view";
import { Icon } from "./icon";
import { IconButton } from "./icon-button";
import { glyphs } from "./icons";
import { FeatureOff, useFormLock } from "./integrations";
import { Markdown } from "./markdown";
import { Menu, type MenuItem } from "./menu";
import { useRetrying } from "./on-demand";
import { Questions, type QuestionsAnswer } from "./questions";
import { SchemaForm } from "./schema-form";
import { type Segment, SegmentedFilter } from "./segmented-filter";
import { type Sent, Unsent, useSending } from "./sending";
import { FOLDED_LINES, SourceView } from "./source-view";
import { ASKING, FEEDBACK } from "./states";
import { StatusBadge, type Tone } from "./status-badge";
import { TextField } from "./text-field";
import { useCoarsePointer } from "./touch";
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
  const { pending, thumb, why } = useThumbs(onThumbs);
  return (
    <fieldset aria-label="Feedback" className="m-0 flex min-w-0 flex-col gap-1 border-0 p-0">
      <span className="flex gap-1">
        <IconButton
          label="Helpful"
          icon={glyphs.thumbsUp}
          aria-pressed={given?.up === true}
          disabled={pending}
          focusableWhenDisabled
          onClick={() => thumb(true)}
        />
        <IconButton
          label="Not helpful"
          icon={glyphs.thumbsDown}
          aria-pressed={given?.up === false}
          disabled={pending}
          focusableWhenDisabled
          onClick={() => thumb(false)}
        />
      </span>
      {why(given)}
    </fieldset>
  );
}

/**
 * A page's actions as a row: its own, then an overflow menu holding thumbs on it as items checked
 * as they stand (portalr ADR-0080). A thumb given opens the "why" under the row, as `Thumbs` does.
 */
export function ActionsMenu({
  label,
  given,
  onThumbs,
  items = [],
  open,
  onOpenChange,
  unseen = false,
}: {
  /** Whether its button is for a screen reader alone, as where a long press opens it. */
  unseen?: boolean;
  /** The menu's name, such as "Artifact actions". */
  label: string;
  given: Thumb | null;
  /** Give thumbs; without it, the menu holds the actions alone. */
  onThumbs?: GiveThumbs;
  /** The actions before the thumbs, if any. */
  items?: readonly MenuItem[];
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}) {
  const { pending, thumb, why } = useThumbs(onThumbs ?? NO_THUMBS);
  return (
    <div className="flex min-w-0 flex-col items-end gap-1">
      {/* Unseen, it shows once the keyboard reaches it, never as an invisible stop. */}
      <span className={unseen ? "sr-only start-0 has-focus-visible:not-sr-only" : "contents"}>
        <Menu
          label={label}
          icon={glyphs.more}
          {...(open !== undefined && { open })}
          {...(onOpenChange && { onOpenChange })}
          items={[
            ...items,
            ...(onThumbs
              ? [
                  // The one already given is given: choosing it again sends nothing.
                  {
                    label: "Helpful",
                    checked: given?.up === true,
                    disabled: pending,
                    onSelect: () => given?.up !== true && thumb(true),
                  },
                  {
                    label: "Not helpful",
                    checked: given?.up === false,
                    disabled: pending,
                    onSelect: () => given?.up !== false && thumb(false),
                  },
                ]
              : []),
          ]}
        />
      </span>
      {onThumbs && why(given)}
    </div>
  );
}

const NO_THUMBS: GiveThumbs = async () => ({ outcome: "done" });

/** How long a press is held before it opens a message's actions, where the pointer can't hover. */
const LONG_PRESS_MS = 500;

/** Thumbs sent as given, then why, if the person wants to say: what `Thumbs` and `ActionsMenu` share. */
function useThumbs(onThumbs: GiveThumbs) {
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
  const why = (given: Thumb | null) => (
    <>
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
    </>
  );
  return { pending, thumb, why } as const;
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
  /**
   * Whether the pointer can't hover, as a finger can't: then the actions are a menu, which a long
   * press on the message opens too. Read from the pointer unless a test says.
   */
  coarse?: boolean;
  /** Give thumbs; without it, there are none. */
  onThumbs?: GiveThumbs;
};

/** The lines of a message past which it is folded, with a way to the whole. */
const FOLDED_AFTER = 40;

/**
 * The message grammar (portalr ADR-0081): the reader's words sit on the quiet wash at the end of
 * the line, the agent's unboxed on the page at its start, with the name above each.
 */
const bubble = (mine: boolean) =>
  mine
    ? "min-w-0 max-w-full break-words text-start rounded-(--bubble-radius) bg-subtle px-(--bubble-pad-x) py-(--bubble-pad-y)"
    : "min-w-0 max-w-full break-words";

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
  coarse,
  onThumbs,
}: MessageProps) {
  const name = useId();
  const notice = message.kind === "notice";
  // A long message is folded past its first lines, with a way to the whole (portalr ADR-0080).
  const long = message.content.split("\n").length > FOLDED_AFTER;
  const [whole, setWhole] = useState(false);
  // Where the pointer can't hover, the actions are a menu (portalr ADR-0080), opened by its button
  // or by a long press on the message; what it copied is said for a screen reader.
  const fingers = useCoarsePointer();
  const menu = coarse ?? fingers;
  const [opened, setOpened] = useState(false);
  const [said, setSaid] = useState("");
  const press = useRef<ReturnType<typeof setTimeout> | null>(null);
  const release = () => {
    if (press.current !== null) {
      clearTimeout(press.current);
      press.current = null;
    }
  };
  const copy = () =>
    Promise.resolve()
      .then(() => navigator.clipboard.writeText(message.content))
      .then(
        () => setSaid("Copied as Markdown"),
        () => setSaid("Couldn't copy"),
      );
  return (
    <li
      aria-labelledby={name}
      aria-busy={sending || undefined}
      className={cn(
        "group flex flex-col gap-1",
        // The reader's own sit at the end of the line, in at most 85% of it; the rest at its start
        // (portalr ADR-0081, as amended), in either direction of writing.
        mine
          ? "max-w-[min(85%,var(--bubble-max-width))] items-end self-end"
          : "max-w-[min(100%,var(--bubble-max-width))] items-start self-start",
        notice && "text-muted italic",
      )}
    >
      <span id={name} className={cn("font-semibold text-xs", mine ? "text-fg" : "text-muted")}>
        {author}
      </span>
      <div
        className={notice ? "min-w-0 max-w-full" : bubble(mine)}
        {...(menu &&
          !sending && {
            onPointerDown: () => {
              release();
              press.current = setTimeout(() => setOpened(true), LONG_PRESS_MS);
            },
            onPointerUp: release,
            onPointerCancel: release,
            onPointerMove: release,
            // The browser's own menu on a long press would come over the message's.
            onContextMenu: (event: MouseEvent<HTMLDivElement>) => event.preventDefault(),
          })}
      >
        <div
          className={cn(
            long && !whole && "relative max-h-(--code-block-max-height) overflow-hidden",
          )}
        >
          <Markdown>{message.content}</Markdown>
          {long && !whole && (
            <div
              aria-hidden="true"
              className="absolute inset-x-0 bottom-0 h-16 bg-linear-to-t from-surface to-transparent"
            />
          )}
        </div>
        {long && (
          // One button, kept, so the focus has somewhere to stay as it is pressed.
          <Button
            variant="secondary"
            size="sm"
            className="mt-2"
            aria-expanded={whole}
            onClick={() => setWhole((was) => !was)}
          >
            {whole ? "Show less" : "Show the whole message"}
          </Button>
        )}
      </div>
      <div
        className={cn(
          "flex flex-wrap items-start gap-1",
          !menu && "min-h-7",
          // Where the pointer hovers, the actions show as it rests on the message, or the keyboard
          // reaches them; the row keeps its height, so nothing moves. What was said stays shown.
          !sending &&
            !menu &&
            !thumbs?.comment &&
            `fine:opacity-0 fine:group-focus-within:opacity-100 fine:group-hover:opacity-100 ${FEEDBACK}`,
        )}
      >
        {sending && onSendAgain ? (
          <span className="flex items-center gap-2">
            <span className={TYPE.note}>It may not have been sent.</span>
            <CommandButton onSend={onSendAgain}>Send again</CommandButton>
          </span>
        ) : sending ? (
          <span className={TYPE.note}>Sending…</span>
        ) : menu ? (
          <>
            {/* No glyph under every message (portalr ADR-0085): a long press opens the sheet;
                the trigger is there for a screen reader alone. */}
            <ActionsMenu
              label="Message actions"
              unseen
              given={thumbs}
              {...(onThumbs && { onThumbs })}
              items={[{ label: "Copy as Markdown", onSelect: copy }]}
              open={opened}
              onOpenChange={setOpened}
            />
            <span role="status" className="sr-only">
              {said}
            </span>
          </>
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

/** What a turn shows beyond its words, loaded as the first run streams (portalr ADR-0083). */
const loadStreaming = () => import("./on-demand/streaming");

/**
 * Load what a turn shows beyond its words ahead of the first run: a thread's page calls it as it
 * opens, so a turn's first phase doesn't wait on a round trip.
 */
export function prefetchStreaming(): void {
  loadStreaming().catch(() => {}); // a failure here is heard, and tried again, by the strip
}

/**
 * What a run is streaming, as it arrives, in the bubble its message will have, so nothing moves
 * when the message replaces it: its thinking, folded, then its words; before either, three dots.
 * Nothing of it is announced as it grows (`aria-live="off"` in the log): the posted message is.
 * A run that failed, or was stopped, keeps what it had streamed, quietly, as `ended` says; the
 * thread says a stop as a line of the log, which announces it.
 */
export function Streaming({
  text,
  author,
  live,
  ended,
}: {
  text: string;
  author: string;
  /** The run's live state, for its thinking; without it, the words alone. */
  live?: Artifactr.Live;
  /** How the run ended, where it did before its reply: what it streamed is left as it was. */
  ended?: "failed" | "stopped";
}) {
  const thinking = live?.thinking ?? "";
  // How long it thought, in the add-on's words, loaded ahead as the thread opens.
  const addon = useRetrying(loadStreaming, thinking !== "", live?.phase);
  const state = ended ? "didn't finish" : text ? "is writing" : "is thinking";
  // The start of what streamed may be missing: cut to its cap, or lost to a reconnect.
  const words = live?.truncated ? `…${text}` : text;
  return (
    <li
      className={cn(
        "flex max-w-[min(100%,var(--bubble-max-width))] flex-col items-start gap-1 self-start",
        ended && "opacity-45",
      )}
      aria-live="off"
      aria-busy={ended ? undefined : "true"}
      aria-label={`${author} ${state}`}
    >
      <span className="font-semibold text-muted text-xs">{author}</span>
      {thinking !== "" && (
        // The thinking, folded under a line that says it is thinking, or for how long it
        // thought: live only, never kept, which the panel says. Nothing of it is announced.
        <Disclosure
          summary={
            live && addon ? (
              <addon.Thought live={live} ended={ended} />
            ) : live?.phase === "thinking" && !ended ? (
              "Thinking…"
            ) : (
              "Thought" // how long, once the add-on has loaded
            )
          }
          className={TYPE.note}
        >
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap break-words font-mono text-xs">
            <bdi>{thinking}</bdi>
          </pre>
          <p className="mt-1">Thinking isn't kept: it goes when the page does.</p>
        </Disclosure>
      )}
      {/* Words the model wrote before calling a tool aren't the reply: they fade as it calls. */}
      {(text || !ended) && (
        <div className={cn(bubble(false), !ended && live?.reply === "stale" && "opacity-45")}>
          {text ? <Markdown streaming={!ended}>{words}</Markdown> : <Thinking />}
        </div>
      )}
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
  const list = useRef<HTMLOListElement>(null);
  const end = useRef<HTMLDivElement>(null);
  // Away from the end, and more arrived since (portalr ADR-0080): the way back to the latest is
  // offered, and never while the end is in view, where the page follows what arrives on its own.
  const [away, setAway] = useState(false);
  const [arrived, setArrived] = useState(false);
  useEffect(() => {
    if (end.current === null || list.current === null) {
      return;
    }
    const seeing = new IntersectionObserver(([entry]) => {
      const visible = entry?.isIntersecting ?? true;
      setAway(!visible);
      if (visible) {
        setArrived(false);
      }
    });
    seeing.observe(end.current);
    const growing = new MutationObserver(() => setArrived(true));
    growing.observe(list.current, { childList: true });
    return () => {
      seeing.disconnect();
      growing.disconnect();
    };
  }, []);
  const toLatest = () => {
    const last = list.current?.lastElementChild;
    if (last instanceof HTMLElement) {
      if (!last.hasAttribute("tabindex")) {
        last.tabIndex = -1;
      }
      last.focus({ preventScroll: true });
    }
    end.current?.scrollIntoView({
      block: "end",
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  };
  return (
    <div className="relative">
      <div role="log" aria-label="Messages">
        <ol ref={list} className={cn("flex flex-col gap-4", className)}>
          {children}
        </ol>
      </div>
      <div ref={end} aria-hidden="true" className="h-px" />
      {away && arrived && (
        <div className="pointer-events-none sticky bottom-(--composer-clearance,0px) flex justify-center pb-2">
          <Button
            variant="secondary"
            size="sm"
            className="pointer-events-auto shadow-(--popover-shadow)"
            onClick={toLatest}
          >
            <Icon icon={glyphs.arrowDown} className="size-3.5" />
            Jump to latest
          </Button>
        </div>
      )}
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
          <ButtonLink size="sm" render={open} className="self-start">
            Open its page
          </ButtonLink>
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
            {open && !full && (
              <IconButton label="Open its page" icon={glyphs.fileText} render={open} />
            )}
            <IconButton
              ref={back}
              escapeThrough={full}
              label={full ? "Back to the page" : "Full view"}
              icon={full ? glyphs.minimize2 : glyphs.maximize2}
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
  attach,
  onFiles,
  keep = false,
}: {
  /**
   * Post the message; the text is cleared as it is sent, and comes back if the server refused
   * it. One whose answer never came may have been posted: the thread offers to send it again.
   */
  onSend: (text: string) => Sent;
  disabled?: boolean;
  /** A way to attach files, such as the page's uploader, at the start of the composer's row (portalr ADR-0080). */
  attach?: ReactNode;
  /** Files dropped on the composer, where the page takes them. */
  onFiles?: (files: FileList) => void;
  /**
   * Keep the words on any failure, the connection closing included: for a page with no other way
   * to send them again, as the Threads page, which starts a thread from them, has none.
   */
  keep?: boolean;
}) {
  const [text, setText] = useState("");
  const hint = useId();
  const box = useRef<HTMLTextAreaElement>(null);
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
      // Sent with the button, the focus comes back to the words: with nothing left to send the
      // button is disabled, and a disabled button would drop it (portalr ADR-0079).
      box.current?.focus();
      let refused = false;
      const told = (settled: { outcome: string }) => {
        refused = settled.outcome === "refused";
        return false; // the composer says why, whatever it was
      };
      if (!(await sending(() => onSend(message), told)) && (refused || keep)) {
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
      className="flex flex-col gap-1 rounded-(--composer-radius) border border-edge bg-surface p-(--composer-pad) outline-offset-(--focus-offset) has-[textarea:focus-visible]:outline-(length:--focus-width) has-[textarea:focus-visible]:outline-focus data-over:border-accent"
      onSubmit={submit}
      {...(onFiles && {
        onDragOver: (event: DragEvent<HTMLFormElement>) => {
          // Files alone: text dragged over the composer is the browser's to drop as text.
          if (!event.dataTransfer.types.includes("Files")) {
            return;
          }
          event.preventDefault();
          event.currentTarget.dataset.over = "";
        },
        onDragLeave: (event: DragEvent<HTMLFormElement>) => {
          delete event.currentTarget.dataset.over;
        },
        onDrop: (event: DragEvent<HTMLFormElement>) => {
          delete event.currentTarget.dataset.over;
          if (!event.dataTransfer.types.includes("Files")) {
            return;
          }
          event.preventDefault();
          onFiles(event.dataTransfer.files);
        },
      })}
    >
      <Field.Root className="flex flex-col" disabled={disabled}>
        <Field.Label className="sr-only">Message</Field.Label>
        <Field.Control
          ref={box}
          render={<textarea rows={2} enterKeyHint="send" aria-describedby={hint} />}
          value={text}
          placeholder="Write to the assistant"
          onValueChange={(value) => setText(String(value))}
          onKeyDown={key}
          className="max-h-64 min-h-14 field-sizing-content resize-none bg-transparent px-2.5 py-2 text-base text-fg outline-none placeholder:text-muted data-disabled:cursor-not-allowed data-disabled:text-muted"
        />
      </Field.Root>
      <div className="flex items-center justify-between gap-2 px-2.5 pb-1">
        {attach}
        {/* The keys' hint, the words' description: shown where the row has room, said always. */}
        <span id={hint} className={cn("text-muted text-xs", attach ? "sr-only" : "max-sm:hidden")}>
          Enter sends, Shift+Enter starts a new line
        </span>
        <Button
          type="submit"
          data-send=""
          className="ml-auto"
          disabled={disabled || !text.trim()}
          pending={pending}
        >
          {/* Its arrow alone on a phone, where the row is narrow; still named Send (portalr ADR-0087). */}
          <span className="sr-only">Send</span>
          <span aria-hidden="true" className="phone:hidden">
            Send
          </span>
          <Icon icon={glyphs.arrowRight} className="size-3.5" />
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
    <div className={cn(card, "gap-3", ended === undefined && off === null && ASKING)}>
      <p className={cn(TYPE.note, "inline-flex items-center gap-1.5")}>
        <Icon icon={glyphs.bot} className="size-3.5" />
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
    // A phone's thumb bar mirrors Approve (portalr ADR-0082) only where there is nothing to
    // review: a reviewed approval is read before it is given, never a press away on the bar.
    const plain = !request.review;
    return (
      <section className={cn(card, "gap-3", ASKING)} aria-label={`Approve ${request.tool_name}?`}>
        {/* A head line, as a question's (portalr ADR-0085): what is asked, then what it does. */}
        <p className={TYPE.subsection}>
          Approve <code className="font-mono">{request.tool_name}</code>?
        </p>
        <Review review={request.review ?? {}} />
        {args && (
          <pre className="overflow-x-auto rounded-(--code-block-radius) border border-line bg-paper p-(--code-panel-pad) font-mono text-xs">
            {unhidden(JSON.stringify(request.args, null, 2))}
          </pre>
        )}
        <span className="flex gap-2 sm:justify-end">
          <Button
            ref={first}
            disabled={answered}
            pending={pending}
            onClick={() => void answer({ approved: true })}
            {...(plain && { "data-thumb-action": "" })}
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
      {/* Read-only once sent, not disabled: Enter in it doesn't drop the focus (portalr ADR-0079). */}
      <TextField label="Answer" name="answer" ref={first} readOnly={closed} required />
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
  id,
  children,
}: {
  proposal: Artifactr.Proposal;
  /** Its id in the page, to link to: focused when followed, and shown so. */
  id?: string | undefined;
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
    <section
      id={id}
      tabIndex={id === undefined ? undefined : -1}
      className={cn(card, "focus:outline-(length:--focus-width) focus:outline-focus")}
      aria-label={`Proposal: ${what}`}
    >
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

/**
 * How long since `from`, once the run has said when it started: "1:05" under an hour, "2:03:40"
 * under a day, "3 d 2 h" past it; nothing for a moment that can't be read.
 */
function elapsed(from: string | undefined, now: Date): string | null {
  const started = from === undefined ? Number.NaN : new Date(from).getTime();
  if (Number.isNaN(started)) {
    return null;
  }
  const seconds = Math.max(0, Math.floor((now.getTime() - started) / 1000));
  const two = (n: number) => String(n).padStart(2, "0");
  if (seconds >= 86_400) {
    return `${Math.floor(seconds / 86_400)} d ${Math.floor((seconds % 86_400) / 3600)} h`;
  }
  if (seconds >= 3600) {
    return `${Math.floor(seconds / 3600)}:${two(Math.floor((seconds % 3600) / 60))}:${two(seconds % 60)}`;
  }
  return `${Math.floor(seconds / 60)}:${two(seconds % 60)}`;
}

/**
 * The strip over a turn under way (portalr ADR-0080): how it is going, what it is doing and for
 * how long (portalr ADR-0083), its tokens, and what can be done about it: Stop while it works,
 * where the reader may; and the way to its question while it waits. One status announces how it
 * goes and, once the add-on that words it has loaded, what it does, as that changes; the clock,
 * the idle count and the tokens are never announced; how the turn ended, the log says: its reply,
 * its failure's notice, or that it was stopped.
 */
export function RunStrip({
  run,
  onStop,
  onQuestion,
  now,
  history,
}: {
  run: Artifactr.Run;
  /** Stop it, where the reader may; none hides Stop. */
  onStop?: () => Sent;
  /** Go to the question it waits on; none hides the way. */
  onQuestion?: () => void;
  /** The moment the elapsed time is counted to, pinned by a test; the strip's own clock otherwise. */
  now?: Date;
  /** The characters of the thread's history the turn was sent, for the estimate; null if unknown. */
  history?: number | null;
}) {
  const active = run.status === "running" || run.status === "paused";
  const [tick, setTick] = useState(() => new Date());
  useEffect(() => {
    if (!active || now !== undefined) {
      return;
    }
    const timer = setInterval(() => setTick(new Date()), 1000);
    return () => clearInterval(timer);
  }, [active, now]);
  const at = now ?? tick;
  const since = elapsed(run.startedAt, at);
  const [tone, status] = RUN_STATUS[run.status];
  const working = run.status === "running";
  // An add-on that failed to load, as offline, is tried again as the next run starts.
  const addon = useRetrying(loadStreaming, working, run.id);
  return (
    // `min-w-0`: a fieldset is otherwise never narrower than its content, as at 200% text.
    <fieldset
      aria-label="This turn"
      // While it waits, the request under it is the surface; the strip is a quiet line above it.
      className={cn(
        "m-0 flex min-w-0 flex-wrap items-center gap-3 rounded-(--card-radius) border border-line bg-surface px-3 py-2",
        run.status === "paused" && "border-transparent bg-transparent",
      )}
    >
      {/* Its status, then what it does and for how long, then its counts: one left edge. */}
      <span className="flex min-w-40 flex-1 flex-col items-start gap-1">
        <StatusBadge tone={tone}>{status}</StatusBadge>
        {/* One status, kept through the add-on's loading, so what it says changes in place. */}
        <span role="status" className="sr-only">
          {working && addon ? <addon.Said run={run} status={status} now={at} /> : status}
        </span>
        {active && (since !== null || (working && addon)) && (
          <span className={`${TYPE.note} flex flex-wrap gap-x-2 tabular-nums`}>
            {working && addon && <addon.Phase run={run} now={at} />}
            {working && addon && since !== null && <span aria-hidden="true">·</span>}
            {since !== null && (
              <span>
                {run.status === "paused" ? "waiting " : <span className="sr-only">for </span>}
                {since}
              </span>
            )}
          </span>
        )}
        {/* The counts, once the add-on has loaded: the thread loads it as it opens. */}
        {/* Folded for everyone (portalr ADR-0085): the strip says how the turn goes; its counts,
            and the model that answered, are a press away. */}
        {working && addon && (
          <Disclosure summary="Tokens" className={TYPE.note}>
            <addon.Tokens run={run} history={history ?? null} />
          </Disclosure>
        )}
      </span>
      <span className="flex shrink-0 items-center gap-2">
        {run.status === "paused" && onQuestion && (
          <Button variant="secondary" size="sm" onClick={onQuestion}>
            Go to the question
          </Button>
        )}
        {working && onStop && <CommandButton onSend={onStop}>Stop</CommandButton>}
      </span>
    </fieldset>
  );
}

/**
 * The thread's mode (portalr ADR-0080), a small toggle in the composer's row beside Attach and
 * Send (ADR-0085): whether the agent edits artifacts itself or proposes changes for someone to
 * accept, a radio group named "Agent mode", switched where the reader may.
 */
export function ModeSwitch({
  mode,
  onChange,
  disabled = false,
}: {
  mode: Artifactr.Thread["mode"];
  onChange: (mode: Artifactr.Thread["mode"]) => Sent;
  disabled?: boolean;
}) {
  const { pending, unsent, send } = useSending();
  return (
    <div className="flex flex-col gap-1">
      <SegmentedFilter
        label="Agent mode"
        size="sm"
        value={mode}
        disabled={disabled || pending}
        segments={MODES}
        onValueChange={(chosen) => void send(() => onChange(chosen))}
      />
      <Unsent reason={unsent} />
    </div>
  );
}

const MODES: readonly Segment<Artifactr.Thread["mode"]>[] = [
  { value: "edit", label: "Auto" },
  { value: "suggest", label: "Ask" },
];

/** How a run is going, announced as it changes. */
export function RunStatus({ status }: { status: Artifactr.Run["status"] }) {
  const [tone, words] = RUN_STATUS[status];
  return (
    <StatusBadge tone={tone} live className="self-start">
      {words}
    </StatusBadge>
  );
}
