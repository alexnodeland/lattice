import { mergeProps } from "@base-ui/react/merge-props";
import { Tooltip } from "@base-ui/react/tooltip";
import type { LucideIcon } from "lucide-react";
import { type ComponentProps, cloneElement, type ReactElement } from "react";
import { Button, buttonLook } from "./button";
import { cn } from "./cn";
import { Icon } from "./icon";

type Named = {
  /** What it does, in words: its name, and the tooltip a pointer or the keyboard shows. */
  label: string;
  icon: LucideIcon;
  className?: string;
  /**
   * Whether Escape, after it closes the tooltip, goes on to what holds the button: for a full
   * view's own way back, so one Escape leaves it. Off by default, so a tooltip's Escape closes
   * the tooltip alone.
   */
  escapeThrough?: boolean;
};

/** An icon button: a button, with a button's props. */
type AsButton = Named &
  Omit<ComponentProps<typeof Button>, "children" | "variant" | "size" | "aria-label" | "render"> & {
    render?: never;
  };

/** An icon link: the link `render` gives, such as the router's, which takes no button props. */
type AsLink = Named & { render: ReactElement };

/** How far the tooltip sits from what it names, in pixels, as Base UI's positioner takes it. */
const OFFSET = 6;

/**
 * An action named by its icon (portalr ADR-0061): a quiet square, a target `--icon-button-size`
 * across, named by `label`, which a tooltip shows when the pointer rests on it or the keyboard
 * reaches it, above a full view (`--tooltip-layer`). A tap on a touch screen doesn't show it: there
 * the icon must be one people know, or a `Button` with its words is the better choice.
 */
export function IconButton(props: AsButton | AsLink) {
  const {
    label,
    icon,
    className,
    render,
    escapeThrough = false,
    ...rest
  } = props as Omit<AsButton, "render"> & {
    render?: ReactElement<object>;
  };
  const square = cn(
    buttonLook("ghost"),
    "size-(--icon-button-size) shrink-0 rounded-(--icon-button-radius) p-0",
    className,
  );
  const glyph = <Icon icon={icon} className="size-(--icon-button-icon)" />;
  return (
    <Tooltip.Root
      onOpenChange={(_, details) => {
        if (escapeThrough && details.reason === "escape-key") details.allowPropagation();
      }}
    >
      {render ? (
        // Named by the label and drawn as the icon, over whatever the link element held; its own
        // handlers and the tooltip's both run.
        <Tooltip.Trigger
          render={(merged) =>
            cloneElement(
              render,
              mergeProps(render.props, merged, { "aria-label": label, children: glyph }),
            )
          }
          className={square}
        />
      ) : (
        <Tooltip.Trigger
          render={<Button {...rest} variant="ghost" aria-label={label} className={square} />}
        >
          {glyph}
        </Tooltip.Trigger>
      )}
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={OFFSET} className="z-(--tooltip-layer)">
          <Tooltip.Popup className="rounded-(--tooltip-radius) border border-edge bg-surface px-(--tooltip-pad-x) py-(--tooltip-pad-y) text-fg text-xs shadow-(--tooltip-shadow)">
            {label}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
