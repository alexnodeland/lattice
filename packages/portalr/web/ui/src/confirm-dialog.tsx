import { AlertDialog } from "@base-ui/react/alert-dialog";
import { type FormEvent, type ReactNode, useRef, useState } from "react";
import { Button } from "./button";
import { actions, backdrop, description, title as heading, popup } from "./dialog";
import { TextField } from "./text-field";

/**
 * A destructive action, confirmed: its trigger opens a Base UI alert dialog that says what will
 * be lost, with the action in the danger colour. The focus starts on Cancel; with `typed`, it starts
 * in the field, and the action waits until that name is typed, as deleting a tenant does, which
 * Enter then sends. The dialog closes once `onConfirm` is done; if it throws, it stays open and
 * says why.
 */
export function ConfirmDialog({
  label,
  name,
  title,
  children,
  confirm,
  typed,
  onConfirm,
}: {
  /** The trigger's words, such as "Archive". */
  label: string;
  /** The trigger's accessible name, where its words alone don't say what it acts on. */
  name?: string;
  /** The question, such as "Archive portalr:triage?". */
  title: string;
  /** What will be lost. */
  children: ReactNode;
  /** The action's words, such as "Archive the rule". */
  confirm: string;
  /** A name to type before the action is allowed. */
  typed?: string;
  onConfirm: () => Promise<unknown>;
}) {
  const [open, setOpen] = useState(false);
  const [entered, setEntered] = useState("");
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
      await onConfirm();
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
        setFailed(null);
      }}
    >
      <AlertDialog.Trigger render={<Button variant="secondary" aria-label={name} />}>
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
            {failed && <p role="alert">{failed}</p>}
            <div className={actions}>
              <AlertDialog.Close ref={cancel} render={<Button variant="secondary" />}>
                Cancel
              </AlertDialog.Close>
              <Button type="submit" variant="danger" aria-busy={pending} disabled={!ready}>
                {confirm}
              </Button>
            </div>
          </form>
        </AlertDialog.Popup>
      </AlertDialog.Portal>
    </AlertDialog.Root>
  );
}
