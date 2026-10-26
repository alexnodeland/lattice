import { Menu as BaseMenu } from "@base-ui/react/menu";
import type { Ref } from "react";
import { Button } from "./button";
import { Icon } from "./icon";
import { IconButton } from "./icon-button";
import type { Glyph } from "./icons";
import { glyphs } from "./icons";
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
  /**
   * A state the item holds, shown as a check when it is on: choosing it asks for the other state.
   * Without it, the item is a plain action.
   */
  readonly checked?: boolean;
}

/**
 * A button that opens a menu of actions. `triggerRef` names the button, for focus to return to.
 * With `icon`, the button is an icon button named `label`: the overflow of a row of actions.
 */
export function Menu({
  label,
  icon,
  items,
  triggerRef,
}: {
  label: string;
  icon?: Glyph;
  items: readonly MenuItem[];
  triggerRef?: Ref<HTMLButtonElement>;
}) {
  return (
    <BaseMenu.Root>
      {icon ? (
        <BaseMenu.Trigger ref={triggerRef} render={<IconButton label={label} icon={icon} />} />
      ) : (
        <BaseMenu.Trigger ref={triggerRef} render={<Button variant="secondary" />}>
          {label}
        </BaseMenu.Trigger>
      )}
      <BaseMenu.Portal>
        <BaseMenu.Positioner sideOffset={4} align="end" className="z-30">
          <BaseMenu.Popup className={popup}>
            {items.map((each) =>
              each.checked === undefined ? (
                <BaseMenu.Item
                  key={each.label}
                  className={item}
                  disabled={each.disabled ?? false}
                  onClick={each.onSelect}
                >
                  {each.label}
                </BaseMenu.Item>
              ) : (
                <BaseMenu.CheckboxItem
                  key={each.label}
                  className={item}
                  disabled={each.disabled ?? false}
                  checked={each.checked}
                  closeOnClick
                  onCheckedChange={each.onSelect}
                >
                  {each.label}
                  <BaseMenu.CheckboxItemIndicator keepMounted className="data-unchecked:invisible">
                    <Icon icon={glyphs.check} className="size-3.5" />
                  </BaseMenu.CheckboxItemIndicator>
                </BaseMenu.CheckboxItem>
              ),
            )}
          </BaseMenu.Popup>
        </BaseMenu.Positioner>
      </BaseMenu.Portal>
    </BaseMenu.Root>
  );
}
