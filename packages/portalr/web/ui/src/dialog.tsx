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
import { keepTabWithin } from "./full-view";
import { SheetHandle, sheet, useSheet } from "./sheet";
import { TYPE } from "./type";

export const backdrop =
  "fixed inset-0 z-40 bg-scrim backdrop-blur-(--dialog-scrim-blur) transition-[opacity,backdrop-filter] duration-(--dialog-duration) data-ending-style:opacity-0 data-ending-style:backdrop-blur-none data-starting-style:opacity-0 data-starting-style:backdrop-blur-none motion-reduce:transition-none";

export const popup =
  "fixed top-1/2 left-1/2 z-50 flex max-h-[85dvh] w-[min(var(--dialog-width),calc(100vw-var(--dialog-margin)))] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-(--dialog-radius) border border-line bg-surface p-(--dialog-pad) text-fg shadow-(--dialog-shadow) outline-none transition-[opacity,scale] duration-(--dialog-duration) data-ending-style:scale-(--dialog-enter-scale) data-starting-style:scale-(--dialog-enter-scale) data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

/** A dialog's title is a section's heading, and what it's about a line under it, on the type scale. */
export const title = TYPE.section;

export const description = TYPE.meta;

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
  title: ReactNode;
  description?: ReactNode;
  /** The words on the button that closes it. */
  close?: string;
  initialFocus?: RefObject<HTMLElement | null>;
  finalFocus?: RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  // On a phone it is a sheet, dragged down to close (portalr ADR-0082).
  const asSheet = useSheet(open, () => onOpenChange(false));
  return (
    <BaseDialog.Root open={open} onOpenChange={onOpenChange}>
      <BaseDialog.Portal>
        <BaseDialog.Backdrop className={backdrop} />
        <BaseDialog.Popup
          ref={asSheet}
          // Base UI traps the focus but doesn't say so: assistive technology learns the page
          // behind is out of reach from aria-modal, as the drawer says it.
          aria-modal="true"
          // Tab kept in it at once, never on Base UI's guards outside it (portalr ADR-0068).
          onKeyDown={(event) => keepTabWithin(event.currentTarget, event.nativeEvent)}
          className={`${popup} ${sheet}`}
          {...(initialFocus && { initialFocus })}
          {...(finalFocus && { finalFocus })}
        >
          <SheetHandle />
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

// The window's safe areas kept clear on a phone, the notch and the home indicator (portalr ADR-0080).
const whole =
  "fixed inset-0 z-50 flex flex-col bg-surface pt-[env(safe-area-inset-top)] pr-[env(safe-area-inset-right)] pb-[env(safe-area-inset-bottom)] pl-[env(safe-area-inset-left)] text-fg outline-none transition-[opacity,scale] duration-(--dialog-duration) data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

/**
 * A dialog that fills the window, for a part that needs all of it, such as a diagram's canvas: its
 * title and a way to close it in a bar along its top, what it holds below. Focus is kept in it as
 * in `Dialog`, and goes to `finalFocus`, or back where it was, when it closes. What it holds is
 * drawn only while it is open. `bar` takes the Close button's place, for a part that asks before
 * it is closed, such as an editor with unsaved changes.
 */
export function WholeDialog({
  open,
  onOpenChange,
  title: named,
  close = "Close",
  describedBy,
  finalFocus,
  bar,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** The words on the button that closes it. */
  close?: string;
  /** The id of what describes it, such as a diagram's text version. */
  describedBy?: string;
  finalFocus?: RefObject<HTMLElement | null>;
  /** What the bar holds in place of its Close button. */
  bar?: ReactNode;
  children: ReactNode;
}) {
  return (
    <BaseDialog.Root open={open} onOpenChange={onOpenChange}>
      <BaseDialog.Portal>
        <BaseDialog.Popup
          aria-modal="true"
          {...(describedBy && { "aria-describedby": describedBy })}
          onKeyDown={(event) => keepTabWithin(event.currentTarget, event.nativeEvent)}
          className={whole}
          {...(finalFocus && { finalFocus })}
        >
          <div className="flex shrink-0 items-center gap-3 border-line border-b px-4 py-2">
            <BaseDialog.Title className={`${TYPE.subsection} me-auto min-w-0 truncate`}>
              {named}
            </BaseDialog.Title>
            {bar ?? (
              <BaseDialog.Close render={<Button variant="secondary" size="sm" />}>
                {close}
              </BaseDialog.Close>
            )}
          </div>
          <div className="relative min-h-0 flex-1">{open && children}</div>
        </BaseDialog.Popup>
      </BaseDialog.Portal>
    </BaseDialog.Root>
  );
}
