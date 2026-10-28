import { Dialog } from "@base-ui/react/dialog";
import type { ReactNode, RefObject } from "react";
import { backdrop } from "./dialog";

/**
 * A palette's frame (portalr ADR-0087): a dialog near the top of the window, over the scrim, a
 * dialog's width, that holds a field and what it finds; `docked`, a phone's tab bar turned into
 * the field, along the window's foot, what it finds above it. The focus starts in it, stays in it
 * while it is open, and goes to `finalFocus` when it closes.
 */
export function PaletteFrame({
  open,
  onOpenChange,
  title,
  finalFocus,
  docked = false,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Its name, said, not shown: the field says what it is for. */
  title: string;
  finalFocus: RefObject<HTMLElement | null>;
  docked?: boolean;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className={backdrop} />
        <Dialog.Popup
          aria-modal="true"
          finalFocus={finalFocus}
          data-docked={docked || undefined}
          className={
            docked
              ? // On the on-screen keyboard, as the composer's dock is (`--keyboard-inset`).
                "fixed inset-x-0 bottom-(--keyboard-inset,0px) z-50 flex max-h-[76dvh] flex-col overflow-hidden border-line border-t bg-surface text-fg outline-none"
              : "fixed top-[12dvh] left-1/2 z-50 flex max-h-[76dvh] w-[min(var(--dialog-width),calc(100vw-var(--dialog-margin)))] -translate-x-1/2 flex-col overflow-hidden rounded-(--dialog-radius) border border-line bg-surface text-fg shadow-(--dialog-shadow) outline-none"
          }
        >
          <Dialog.Title className="sr-only">{title}</Dialog.Title>
          {children}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
