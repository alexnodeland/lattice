/**
 * A dialog over the page, and the look the kit's dialogs share: Base UI's Dialog on the surface,
 * over the scrim, with its title, what it's about, what it holds, and its actions at its end. The
 * backdrop, which blurs what is behind it a little, is the drawer's too, and the rest
 * ConfirmDialog's, whose open and close match the drawer's slide. A dialog and a drawer cast the
 * most shadow there is (portalr ADR-0039).
 */

import { Dialog as BaseDialog } from "@base-ui/react/dialog";
import type { ReactNode, RefObject } from "react";
import { Button } from "./button";

export const backdrop =
  "fixed inset-0 z-40 bg-scrim backdrop-blur-(--dialog-scrim-blur) transition-[opacity,backdrop-filter] duration-(--dialog-duration) data-ending-style:opacity-0 data-ending-style:backdrop-blur-none data-starting-style:opacity-0 data-starting-style:backdrop-blur-none motion-reduce:transition-none";

export const popup =
  "fixed top-1/2 left-1/2 z-50 flex max-h-[85dvh] w-[min(var(--dialog-width),calc(100vw-var(--dialog-margin)))] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-(--dialog-radius) border border-line bg-surface p-(--dialog-pad) text-fg shadow-(--dialog-shadow) outline-none transition-[opacity,scale] duration-(--dialog-duration) data-ending-style:scale-(--dialog-enter-scale) data-starting-style:scale-(--dialog-enter-scale) data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

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
