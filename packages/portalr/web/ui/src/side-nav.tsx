import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";
import type { Glyph } from "./icons";
import { FEEDBACK, RING } from "./states";

/** The areas of a workspace, as a list of links, the current one marked. */
export function SideNav({ label, children }: { label: string; children: ReactNode }) {
  return (
    <nav aria-label={label}>
      <ul className="flex flex-col gap-0.5">{children}</ul>
    </nav>
  );
}

type NavLinkProps = Omit<ComponentProps<"a">, "className" | "children"> & {
  /** What to render as the link, such as the router's own, which marks the current page. */
  render?: ReactElement;
  /** The area's icon, beside its word. */
  icon?: Glyph;
  /** How many wait for the reader there, said as such. */
  count?: number;
  children: string;
};

/**
 * One area: its icon, its word, and how many wait there. `aria-current="page"` marks the area
 * shown, and `aria-current="true"` the area a page inside it belongs to: in the text's colour and
 * weight where the others are quiet, with a rule in the working colour at its start (portalr
 * ADR-0080). Under forced colours, where the working colour is the system's, the current one keeps an inset outline
 * in the system's highlight, as a selected tab keeps its border; focused, the ring goes back outside.
 */
export function NavLink({ render, icon, count, children, ...props }: NavLinkProps) {
  const link = useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        "aria-label": count ? `${children}, ${count} waiting for you` : undefined,
        className: cn(
          RING,
          FEEDBACK,
          "flex items-center gap-2.5 rounded-(--nav-radius) px-(--nav-pad-x) py-(--nav-pad-y) font-medium text-fg text-sm hover:bg-subtle aria-[current=page]:bg-wash aria-[current=page]:text-accent aria-[current=true]:bg-wash aria-[current=true]:text-accent forced-colors:aria-[current=page]:outline-solid forced-colors:aria-[current=page]:outline-(length:--focus-width) forced-colors:aria-[current=page]:-outline-offset-(--focus-width) forced-colors:aria-[current=page]:outline-system-highlight forced-colors:aria-[current=page]:focus-visible:outline-offset-(--focus-offset) forced-colors:aria-[current=page]:focus-visible:outline-focus forced-colors:aria-[current=true]:outline-solid forced-colors:aria-[current=true]:outline-(length:--focus-width) forced-colors:aria-[current=true]:-outline-offset-(--focus-width) forced-colors:aria-[current=true]:outline-system-highlight forced-colors:aria-[current=true]:focus-visible:outline-offset-(--focus-offset) forced-colors:aria-[current=true]:focus-visible:outline-focus",
        ),
        children: (
          <>
            {icon && <Icon icon={icon} />}
            {children}
            {count ? (
              <span
                aria-hidden="true"
                className="ml-auto font-mono text-accent text-xs tabular-nums"
              >
                {count}
              </span>
            ) : null}
          </>
        ),
      },
      props,
    ),
  });
  return <li>{link}</li>;
}
