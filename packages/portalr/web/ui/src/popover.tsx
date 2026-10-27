import { Popover as BasePopover } from "@base-ui/react/popover";
import type { ReactElement, ReactNode } from "react";
import { cn } from "./cn";
import { popover } from "./menu";

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
  return (
    <BasePopover.Root open={open} onOpenChange={onOpenChange}>
      <BasePopover.Trigger render={trigger} />
      <BasePopover.Portal>
        <BasePopover.Positioner side="top" align="start" sideOffset={8} className="z-30">
          <BasePopover.Popup
            role="dialog"
            aria-label={label}
            {...(initialFocus && { initialFocus })}
            className={cn(
              popover,
              "flex flex-col gap-3 p-(--card-pad) outline-none transition-[opacity,scale] duration-(--popover-duration) data-ending-style:scale-(--popover-enter-scale) data-starting-style:scale-(--popover-enter-scale) data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none",
              className,
            )}
          >
            {children}
          </BasePopover.Popup>
        </BasePopover.Positioner>
      </BasePopover.Portal>
    </BasePopover.Root>
  );
}
