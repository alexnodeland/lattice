/**
 * A dialog over the page, and the look the kit's dialogs share: Base UI's Dialog on the surface,
 * over the scrim, with its title, what it's about, what it holds, and its actions at its end. The
 * backdrop is the drawer's too, and the rest ConfirmDialog's, whose open and close match the
 * drawer's slide.
 */

import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import type { ReactNode, RefObject } from "react";
import { Button } from "./button";

export const backdrop =
  "fixed inset-0 z-40 bg-scrim transition-opacity duration-200 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

export const popup =
  "fixed top-1/2 left-1/2 z-50 flex max-h-[85dvh] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-lg border border-line bg-surface p-5 text-fg shadow-lg outline-none transition-[opacity,scale] duration-200 data-ending-style:scale-98 data-starting-style:scale-98 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

export const title = "font-semibold text-fg text-lg";

export const description = "text-muted text-sm";

export const actions = "flex flex-wrap justify-end gap-2";

/**
 * A dialog its caller opens: its title, what it's about, what it holds, and a way to close it.
 * Focus stays in it while it's open: it starts at `initialFocus`, or its first control, and goes
 * to `finalFocus`, or back where it was, when it closes.
 */
export function Dialog({
  open,
  onOpenChange,
  title: named,
  description: about,
  close = "Close",
  initialFocus,
  finalFocus,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: ReactNode;
  /** The words on the button that closes it. */
  close?: string;
  initialFocus?: RefObject<HTMLElement | null>;
  finalFocus?: RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  return (
    <BaseDialog.Root open={open} onOpenChange={onOpenChange}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className={backdrop} />
        <BaseDialog.Popup
          className={popup}
          {...(initialFocus && { initialFocus })}
          {...(finalFocus && { finalFocus })}
        >
          <BaseDialog.Title className={title}>{named}</BaseDialog.Title>
          {about && (
            <BaseDialog.Description className={description}>{about}</BaseDialog.Description>
          )}
          {children}
          <div className={actions}>
            <BaseDialog.Close render={<Button variant="secondary" />}>{close}</BaseDialog.Close>
          </div>
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}
