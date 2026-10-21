import { Collapsible } from "@base-ui/react/collapsible";
import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";

/**
 * How a disclosure's trigger looks (portalr ADR-0063):
 * - `quiet`, a muted line such as "Show the figures";
 * - `link`, in the working colour, underlined on hover, for a part that reads as a way on;
 * - `block`, the whole width of what it opens, laid out by its summary, as a card's header is.
 */
const LOOK = {
  quiet: "text-muted hover:text-fg",
  link: "text-accent underline-offset-2 hover:underline",
  block: "w-full items-start text-start hover:bg-wash",
} as const;

/**
 * A part that opens and closes: its summary on a button that says whether it is open
 * (`aria-expanded`) and what it opens (`aria-controls`), by the keyboard as by a pointer, with the
 * kit's focus ring and a target at least `--disclosure-target` tall, and a chevron that turns as
 * fast as the kit's motion allows, not at all under reduced motion. What it opens stays in the page
 * while closed, hidden until found, as a `details` element's does, so a find in the page reaches it.
 */
export function Disclosure({
  summary,
  look = "quiet",
  open,
  defaultOpen,
  onOpenChange,
  className,
  triggerClassName,
  panelClassName,
  children,
}: {
  summary: ReactNode;
  look?: keyof typeof LOOK;
  /** Open or not, where the caller holds it; or open at first, where the disclosure does. */
  open?: boolean;
  defaultOpen?: boolean;
  onOpenChange?: (open: boolean) => void;
  /** The root's box: its edge or fill, as a card's. `data-open` marks it open. */
  className?: string;
  /** The trigger's layout, such as a block's padding: never its colour. */
  triggerClassName?: string;
  /** What it opens: its spacing. */
  panelClassName?: string;
  children: ReactNode;
}) {
  return (
    <Collapsible.Root
      {...(open !== undefined && { open })}
      {...(defaultOpen !== undefined && { defaultOpen })}
      {...(onOpenChange && { onOpenChange: (next: boolean) => onOpenChange(next) })}
      className={className}
    >
      <Collapsible.Trigger
        className={cn(
          "group flex min-h-(--disclosure-target) cursor-pointer gap-(--disclosure-gap) rounded-(--disclosure-radius) outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus",
          look !== "block" && "items-center",
          LOOK[look],
          triggerClassName,
        )}
      >
        <Icon
          icon={ChevronRight}
          className={cn(
            "size-3.5 shrink-0 text-muted transition-transform duration-(--disclosure-duration) group-data-panel-open:rotate-90 motion-reduce:transition-none rtl:-scale-x-100 rtl:group-data-panel-open:rotate-90",
            look === "block" && "mt-0.5 size-4",
          )}
        />
        {summary}
      </Collapsible.Trigger>
      <Collapsible.Panel
        hiddenUntilFound
        className={cn("pt-(--disclosure-panel-gap)", panelClassName)}
      >
        {children}
      </Collapsible.Panel>
    </Collapsible.Root>
  );
}
