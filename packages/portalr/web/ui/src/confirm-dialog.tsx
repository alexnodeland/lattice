import { AlertDialog } from "@base-ui/react/alert-dialog";
import { type FormEvent, type ReactNode, useRef, useState } from "react";
import { Button } from "./button";
import { actions, backdrop, description, title as heading, popup } from "./dialog";
import { TextField } from "./text-field";

/** The most a reason may be, in characters. */
const MOST_REASON = 500;

/**
 * A destructive action, confirmed: its trigger opens a Base UI alert dialog that says what will
 * be lost, with the action in the danger colour. The focus starts on Cancel; with `typed`, it starts
 * in the field, and the action waits until that name is typed, as deleting a tenant does, which
 * Enter then sends. With `asking`, it also asks for a reason, which is optional and goes to
 * `onConfirm`; with `calm`, the action is in the primary colour, for one that loses nothing. The
 * dialog closes once `onConfirm` is done; if it throws, it stays open and says why.
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
  /** What to do, with the reason given, if it was asked for; it ends the dialog if it doesn't throw. */
  onConfirm: (reason: string) => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [entered, setEntered] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState(false);
  const [failed, setFailed] = useState<string | null>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  const ready = !pending && (typed === undefined || entered === typed);
  async function act(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!ready) {
      return;
    }
    setPending(true);
    setFailed(null);
    try {
      await onConfirm(reason.trim());
      setOpen(false);
    } catch (error) {
      setFailed(error instanceof Error ? error.message : String(error));
    } finally {
      setPending(false);
    }
  }
  return (
    <AlertDialog.Root
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
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
