import { Menu as BaseMenu } from "@base-ui/react/menu";
import type { Ref } from "react";
import { Button } from "./button";
import { FEEDBACK } from "./states";

/**
 * A menu of actions, and the look the kit's menus share: Base UI's Menu, on the surface. The item the keyboard or the
 * pointer is on is washed, in the working colour, and ringed in the focus colour, which stands 3:1
 * or more from the surface where the wash alone would not.
 */

/** The surface everything that floats over the page shares: a menu, a select's list of choices, and a chart's tooltip. */
export const popover =
  "rounded-(--popover-radius) border border-edge bg-surface text-fg text-sm shadow-(--popover-shadow)";

export const popup = `${popover} min-w-56 p-(--popover-pad) outline-none transition-[opacity,scale] duration-(--popover-duration) data-ending-style:scale-(--popover-enter-scale) data-starting-style:scale-(--popover-enter-scale) data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none`;

export const groupLabel = "px-(--popover-item-pad-x) pt-1.5 pb-1 font-semibold text-muted text-xs";

export const item = `flex cursor-default items-center justify-between gap-3 rounded-(--popover-item-radius) px-(--popover-item-pad-x) py-(--popover-item-pad-y) outline-none data-highlighted:bg-wash data-highlighted:text-accent data-highlighted:ring-(length:--focus-width) data-highlighted:ring-focus data-highlighted:ring-inset data-disabled:cursor-not-allowed data-disabled:text-muted ${FEEDBACK}`;

export const separator = "my-1.5 h-px bg-line";

/** One of a menu's actions. */
export interface MenuItem {
  readonly label: string;
  readonly onSelect: () => void;
  /** Whether it can't be chosen now, such as while it is being done. */
  readonly disabled?: boolean;
}

/** A button that opens a menu of actions. `triggerRef` names the button, for focus to return to. */
export function Menu({
  label,
  items,
  triggerRef,
}: {
  label: string;
  items: readonly MenuItem[];
  triggerRef?: Ref<HTMLButtonElement>;
}) {
  return (
    <BaseMenu.Root>
      <BaseMenu.Trigger ref={triggerRef} render={<Button variant="secondary" />}>
        {label}
      </BaseMenu.Trigger>
      <BaseMenu.Portal>
        <BaseMenu.Positioner sideOffset={4} align="end" className="z-30">
          <BaseMenu.Popup className={popup}>
            {items.map((each) => (
              <BaseMenu.Item
                key={each.label}
                className={item}
                disabled={each.disabled ?? false}
                onClick={each.onSelect}
              >
                {each.label}
              </BaseMenu.Item>
            ))}
          </BaseMenu.Popup>
        </BaseMenu.Positioner>
      </BaseMenu.Portal>
    </BaseMenu.Root>
  );
}
