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
  const { label, icon, className, render, ...rest } = props as AsButton & { render?: ReactElement };
  const square = cn(
    buttonLook("ghost"),
    "size-(--icon-button-size) shrink-0 rounded-(--icon-button-radius) p-0",
    className,
  );
  const glyph = <Icon icon={icon} className="size-(--icon-button-icon)" />;
  return (
    <Tooltip.Root
      onOpenChange={(_, details) => {
        // Escape closes the tooltip and goes on to what holds it, such as a full view, which a
        // tooltip has no reason to keep open.
        if (details.reason === "escape-key") details.allowPropagation();
      }}
    >
      {render ? (
        // Named by the label and drawn as the icon, over whatever the link element held.
        <Tooltip.Trigger
          render={(merged) =>
            cloneElement(render, { ...merged, "aria-label": label, children: glyph })
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
