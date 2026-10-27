import { AlertDialog } from "@base-ui/react/alert-dialog";
import {
  type FormEvent,
  type ReactNode,
  type RefObject,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { Alert } from "./alert";
import { Button, type ButtonSize, type ButtonVariant } from "./button";
import { actions, backdrop, description, title as heading, popup } from "./dialog";
import { failureLogged, failureSaid } from "./failure";
import { keepTabWithin } from "./full-view";
import { sheet } from "./sheet";
import { TextField } from "./text-field";

/** The most a reason may be, in characters. */
const MOST_REASON = 500;

/**
 * An action that can't be taken back, or does something outside, confirmed: its trigger opens a Base UI alert dialog that says what will
 * be lost, with the action in the danger colour. The focus starts on its way out, which is Cancel unless `dismiss` words it otherwise; with `typed`, it starts
 * in the field, and the action waits until that name is typed, as deleting a tenant does, which
 * Enter then sends. With `asking`, it also asks for a reason, which is optional and goes to
 * `onConfirm`; with `calm`, the action is in the primary colour, for one that loses nothing but is
 * confirmed all the same, such as running something again. The dialog closes once `onConfirm` is
 * done, and the action is sent once however often it is submitted meanwhile; if it throws, it
 * stays open and says why. `onOpenChange` hears each time it opens and closes.
 */
export function ConfirmDialog({
  label,
  about,
  look = "secondary",
  size = "md",
  dismiss = "Cancel",
  className,
  title,
  children,
  confirm,
  typed,
  asking,
  calm = false,
  disabled = false,
  finalFocus,
  returnTo,
  onOpenChange,
  onConfirm,
}: {
  /** The trigger's words, such as "Archive". */
  label: string;
  /**
   * What the trigger acts on, such as "alice": read aloud after its words, "Remove alice", and not
   * shown, so a row of them says "Remove" and no more.
   */
  about?: string;
  /** The trigger's look: a row's action is `ghost`, and a destructive one offered `danger-soft`. */
  look?: ButtonVariant;
  /** The trigger's size: `sm` for an action in a row. */
  size?: ButtonSize;
  /** The words of the way out, `Cancel` unless it would stand beside another, such as "Keep running". */
  dismiss?: string;
  /** The trigger's classes, beside its own, such as where it sits in a form. */
  className?: string | undefined;
  /** The question, such as "Archive portalr:triage?". */
  title: string;
  /** What will be lost. */
  children: ReactNode;
  /** The action's words, such as "Archive the rule". */
  confirm: string;
  /** A name to type before the action is allowed. */
  typed?: string;
  /** The label of an optional reason to ask for, such as "Reason (optional)". */
  asking?: string;
  /** Whether the action is one that loses nothing, so it isn't in the danger colour. */
  calm?: boolean;
  /**
   * Where focus goes when the action is done, if not back to the trigger, such as a trigger that
   * is then disabled. Cancelling, Escape and the backdrop send it back to the trigger as ever.
   */
  finalFocus?: RefObject<HTMLElement | null>;
  /** Whether the trigger can't be used yet, as when what it acts on isn't filled in. */
  disabled?: boolean;
  /**
   * Where focus goes if the dialog is taken away while it is open, along with its trigger, as when
   * what it acts on changes so that it no longer applies. Otherwise focus returns to the trigger.
   */
  returnTo?: RefObject<HTMLElement | null>;
  /** Called when the dialog opens or closes, however it closes. */
  onOpenChange?: (open: boolean) => void;
  /** What to do, with the reason given, if it was asked for; it ends the dialog if it doesn't throw. */
  onConfirm: (reason: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  // Whether the action is under way: read at once, where a state would be a render behind.
  const busy = useRef(false);
  // On a phone the dialog sits as a sheet (portalr ADR-0082), but is not dragged away: a
  // confirm, like an alert, closes only by a choice, as its backdrop doesn't close it either.
  const [entered, setEntered] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  // Whether the dialog closes because the action was done: only then does focus go elsewhere.
  const done = useRef(false);
  const counter = useId();
  const shown = useRef(false);
  shown.current = open;
  useEffect(
    () => () => {
      // Gone while open, with its trigger: focus goes where the caller says, not to the page.
      if (shown.current) {
        returnTo?.current?.focus();
      }
    },
    [returnTo],
  );
  const [failed, setFailed] = useState<string | null>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const ready = !pending && (typed === undefined || entered === typed);
  async function act(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready || busy.current) {
      return;
    }
    busy.current = true;
    setPending(true);
    setFailed(null);
    try {
      await onConfirm(reason.trim());
      done.current = true;
      setOpen(false);
    } catch (error) {
      // An action's error is its caller's words, a refused command's the kit's own (`refusal`);
      // anything else is the kit's sentence for it. The whole failure is for operators, in the
      // console (portalr ADR-0070).
      failureLogged(error);
      setFailed(error instanceof Error ? error.message : failureSaid(error));
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(next) => {
        // A dialog whose action is under way is not dismissed: Escape, the backdrop and Cancel wait.
        if (!next && busy.current) {
          return;
        }
        setOpen(next);
        done.current = false;
        onOpenChange?.(next);
        setEntered("");
        setReason("");
        setFailed(null);
      }}
    >
      <AlertDialog.Trigger
        disabled={disabled}
        render={<Button variant={look} size={size} className={className ?? ""} />}
      >
        {label}
        {about !== undefined && <span className="sr-only"> {about}</span>}
      </AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Backdrop className={backdrop} />
        <AlertDialog.Popup
          className={`${popup} ${sheet}`}
          // Tab kept in it at once, never on Base UI's guards outside it (portalr ADR-0068).
          onKeyDown={(event) => keepTabWithin(event.currentTarget, event.nativeEvent)}
          initialFocus={typed === undefined ? cancel : true}
          {...(finalFocus && { finalFocus: () => (done.current ? finalFocus.current : true) })}
        >
          <AlertDialog.Title className={heading}>{title}</AlertDialog.Title>
          <AlertDialog.Description render={<div />} className={description}>
            {children}
          </AlertDialog.Description>
          <form className="flex flex-col gap-4" onSubmit={(event) => void act(event)}>
            {typed !== undefined && (
              <TextField
                label={`Type ${typed} to confirm`}
                value={entered}
                onValueChange={(value) => setEntered(String(value))}
                autoComplete="off"
              />
            )}
            {asking !== undefined && (
              <TextField
                label={asking}
                aria-describedby={counter}
                value={reason}
                onValueChange={(value) => setReason(String(value))}
                maxLength={MOST_REASON}
                autoComplete="off"
              />
            )}
            {asking !== undefined && (
              <p id={counter} className="text-muted text-xs">
                {reason.length} of {MOST_REASON} characters
              </p>
            )}
            {failed && <Alert tone="error">{failed}</Alert>}
            <div className={actions}>
              <AlertDialog.Close ref={cancel} render={<Button variant="secondary" />}>
                {dismiss}
              </AlertDialog.Close>
              <Button
                type="submit"
                variant={calm ? "primary" : "danger"}
                aria-busy={pending}
                disabled={typed !== undefined && entered !== typed}
                pending={pending}
              >
                {confirm}
              </Button>
            </div>
          </form>
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
