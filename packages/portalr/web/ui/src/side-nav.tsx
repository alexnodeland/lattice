import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { LucideIcon } from "lucide-react";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { Icon } from "./icon";

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
  icon?: LucideIcon;
  /** How many wait for the reader there, said as such. */
  count?: number;
  children: string;
};

/**
 * One area: its icon, its word, and how many wait there. `aria-current="page"` marks the area
 * shown, and `aria-current="true"` the area a page inside it belongs to.
 */
export function NavLink({ render, icon, count, children, ...props }: NavLinkProps) {
  const link = useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        "aria-label": count ? `${children}, ${count} waiting for you` : undefined,
        className:
          "flex items-center gap-2.5 rounded-md px-3 py-2 font-medium text-fg text-sm outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus aria-[current=page]:bg-wash aria-[current=page]:font-semibold aria-[current=page]:text-accent aria-[current=true]:bg-wash aria-[current=true]:font-semibold aria-[current=true]:text-accent",
        children: (
          <>
            {icon && <Icon icon={icon} />}
            {children}
            {count ? (
              <span
                aria-hidden="true"
                className="ml-auto grid h-5 min-w-5 place-items-center rounded-full bg-accent px-1.5 font-semibold text-on-accent text-xs"
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
