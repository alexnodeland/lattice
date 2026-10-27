import { Popover as BasePopover } from "@base-ui/react/popover";
import type { ReactElement, ReactNode } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { backdrop } from "./dialog";
import { popover } from "./menu";
import { SheetHandle, sheetPopup, sheetPositioner, useSheet } from "./sheet";
import { usePhone } from "./touch";

/**
 * A panel that opens from a button, over the page, with a dialog's manners (portalr ADR-0080):
 * Escape, a click outside and the button close it, the focus goes in as it opens and back to the
 * button as it closes, and it is a dialog named `label` to assistive technology. The composer's
 * attach panel is one. `trigger` is the button, which the panel marks expanded.
 */
export function Popover({
  label,
  trigger,
  open,
  onOpenChange,
  initialFocus,
  className,
  children,
}: {
  label: string;
  trigger: ReactElement;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** What takes the focus as it opens: the panel itself unless given. */
  initialFocus?: () => HTMLElement | null;
  className?: string;
  children: ReactNode;
}) {
  // On a phone it is a sheet (portalr ADR-0082), and modal as a dialog is: the page behind it
  // neither scrolls nor takes the focus, under a scrim, with a Done to leave by.
  const phone = usePhone();
  const asSheet = useSheet(open, () => onOpenChange(false));
  return (
    <BasePopover.Root open={open} onOpenChange={onOpenChange} modal={phone}>
      <BasePopover.Trigger render={trigger} />
      <BasePopover.Portal>
        {phone && <BasePopover.Backdrop className={backdrop} />}
        <BasePopover.Positioner
          side="top"
          align="start"
          sideOffset={8}
          className={`z-30 ${sheetPositioner}`}
        >
          <BasePopover.Popup
            ref={asSheet}
            role="dialog"
            aria-label={label}
            aria-modal={phone || undefined}
            {...(initialFocus && { initialFocus })}
            className={cn(
              popover,
              "flex flex-col gap-3 p-(--card-pad) outline-none transition-[opacity,scale] duration-(--popover-duration) data-ending-style:scale-(--popover-enter-scale) data-starting-style:scale-(--popover-enter-scale) data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none",
              sheetPopup,
              className,
            )}
          >
            <SheetHandle />
            {children}
            {phone && (
              <BasePopover.Close render={<Button variant="secondary" className="self-end" />}>
                Done
              </BasePopover.Close>
            )}
          </BasePopover.Popup>
        </BasePopover.Positioner>
      </BasePopover.Portal>
    </BasePopover.Root>
  );
}
