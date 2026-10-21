import { Tooltip } from "@base-ui/react/tooltip";
import type { LucideIcon } from "lucide-react";
import type { ComponentProps, ReactElement } from "react";
import { Button } from "./button";
import { cn } from "./cn";
import { Icon } from "./icon";

type Props = Omit<ComponentProps<typeof Button>, "children" | "variant" | "size" | "aria-label"> & {
  /** What the button does, in words: its name, and the tooltip a pointer or the keyboard shows. */
  label: string;
  icon: LucideIcon;
  /** What to render as the button, such as the router's link: a `<button>` without one. */
  render?: ReactElement;
};

/**
 * An action named by its icon (portalr ADR-0061): a quiet square, a target `--icon-button-size`
 * across, named by `label`, which a tooltip shows when the pointer rests on it or the keyboard
 * reaches it. Where the words matter more than the room, a `Button` with its words is the better
 * choice.
 */
export function IconButton({ label, icon, render, className, ...props }: Props) {
  const square = cn(
    "size-(--icon-button-size) shrink-0 rounded-(--icon-button-radius) p-0",
    className,
  );
  return (
    <Tooltip.Root>
      {render ? (
        // A link: the link's own element, in the button's ghost look, named by the label.
        <Tooltip.Trigger
          render={render}
          aria-label={label}
          className={cn(
            "inline-flex items-center justify-center text-fg outline-offset-(--focus-offset) hover:bg-wash focus-visible:outline-(length:--focus-width) focus-visible:outline-focus",
            square,
          )}
        >
          <Icon icon={icon} className="size-(--icon-button-icon)" />
        </Tooltip.Trigger>
      ) : (
        <Tooltip.Trigger
          render={<Button variant="ghost" aria-label={label} className={square} {...props} />}
        >
          <Icon icon={icon} className="size-(--icon-button-icon)" />
        </Tooltip.Trigger>
      )}
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={6}>
          <Tooltip.Popup className="rounded-(--tooltip-radius) border border-edge bg-surface px-(--tooltip-pad-x) py-(--tooltip-pad-y) text-fg text-xs shadow-(--tooltip-shadow)">
            {label}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
