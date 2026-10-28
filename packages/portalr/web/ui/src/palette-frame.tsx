import { Dialog } from "@base-ui/react/dialog";
import type { ReactNode, RefObject } from "react";
import { backdrop } from "./dialog";

/**
 * A palette's frame (portalr ADR-0087): a dialog near the top of the window, over the scrim, the
 * width of a reading column, that holds a field and what it finds. The focus starts in it, stays
 * in it while it is open, and goes to `finalFocus` when it closes.
 */
export function PaletteFrame({
  open,
  onOpenChange,
  title,
  finalFocus,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Its name, said, not shown: the field says what it is for. */
  title: string;
  finalFocus: RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Backdrop className={backdrop} />
        <Dialog.Popup
          aria-modal="true"
          finalFocus={finalFocus}
          className="fixed top-[12dvh] left-1/2 z-50 flex max-h-[76dvh] w-[min(36rem,calc(100vw-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-(--dialog-radius) border border-line bg-surface text-fg shadow-(--dialog-shadow) outline-none"
        >
          <Dialog.Title className="sr-only">{title}</Dialog.Title>
          {children}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
