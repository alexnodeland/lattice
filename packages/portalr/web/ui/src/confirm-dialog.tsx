import { AlertDialog } from "@base-ui/react/alert-dialog";
import { type FormEvent, type ReactNode, useRef, useState } from "react";
import { Button } from "./button";
import { actions, backdrop, description, title as heading, popup } from "./dialog";
import { TextField } from "./text-field";

/** The most a reason may be, in characters. */
const MOST_REASON = 500;

/**
 * An action that can't be taken back, or that does something outside, confirmed: its trigger opens a Base UI alert dialog that says what will
 * be lost, with the action in the danger colour. The focus starts on Cancel; with `typed`, it starts
 * in the field, and the action waits until that name is typed, as deleting a tenant does, which
 * Enter then sends. With `asking`, it also asks for a reason, which is optional and goes to
 * `onConfirm`; with `calm`, the action is in the primary colour, for one that loses nothing but is
 * confirmed all the same, such as running something again. The dialog closes once `onConfirm` is
 * done, and the action is sent once however often it is submitted meanwhile; if it throws, it
 * stays open and says why. `onOpenChange` hears each time it opens and closes.
 */
export function ConfirmDialog({
  label,
  name,
  className,
  title,
  children,
  confirm,
  typed,
  asking,
  calm = false,
  onOpenChange,
  onConfirm,
}: {
  /** The trigger's words, such as "Archive". */
  label: string;
  /** The trigger's accessible name, where its words alone don't say what it acts on. */
  name?: string;
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
  /** Called when the dialog opens or closes, however it closes. */
  onOpenChange?: (open: boolean) => void;
  /** What to do, with the reason given, if it was asked for; it ends the dialog if it doesn't throw. */
  onConfirm: (reason: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [entered, setEntered] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  // Whether the action is under way: read at once, where a state would be a render behind.
  const busy = useRef(false);
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
      setOpen(false);
    } catch (error) {
      setFailed(error instanceof Error ? error.message : String(error));
    } finally {
      busy.current = false;
      setPending(false);
    }
  }
  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        onOpenChange?.(next);
        setEntered("");
        setReason("");
        setFailed(null);
      }}
    >
      <AlertDialog.Trigger
        render={<Button variant="secondary" aria-label={name} className={className ?? ""} />}
      >
        {label}
      </AlertDialog.Trigger>
      <AlertDialog.Portal>
        <AlertDialog.Backdrop className={backdrop} />
        <AlertDialog.Popup className={popup} initialFocus={typed === undefined ? cancel : true}>
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
                value={reason}
                onValueChange={(value) => setReason(String(value))}
                maxLength={MOST_REASON}
                autoComplete="off"
              />
            )}
            {asking !== undefined && (
              <p className="text-muted text-xs">
                {reason.length} of {MOST_REASON} characters
              </p>
            )}
            {failed && <p role="alert">{failed}</p>}
            <div className={actions}>
              <AlertDialog.Close ref={cancel} render={<Button variant="secondary" />}>
                Cancel
              </AlertDialog.Close>
              <Button
                type="submit"
                variant={calm ? "primary" : "danger"}
                aria-busy={pending}
                disabled={!ready}
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
