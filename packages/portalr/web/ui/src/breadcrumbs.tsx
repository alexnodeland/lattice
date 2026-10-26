import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ReactElement } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { FEEDBACK, RING } from "./states";
import { TYPE } from "./type";

/**
 * How a router's link in a crumb matches, as TanStack Router's `activeOptions`: exactly, so the
 * place above isn't marked as the page shown, `aria-current="page"`, while a page below it is.
 */
export const CRUMB = { exact: true } as const;

/** One place above this one: its name, and the link to it, such as the router's own. */
export type Crumb = { label: string } & ({ render: ReactElement } | { href: string });

/** A crumb: a quiet link, in the text's colour when hovered or reached, a target 24px tall or more. */
function CrumbLink({
  render,
  ...props
}: Omit<Crumb, "label"> & { children: string } & { render?: ReactElement; href?: string }) {
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(
          "inline-flex min-h-(--breadcrumb-target) items-center rounded-(--disclosure-radius) text-muted hover:text-fg focus-visible:text-fg",
          RING,
          FEEDBACK,
        ),
      },
      props,
    ),
  });
}

/**
 * The way back up (portalr ADR-0059, ADR-0080): the places above this page, outermost first,
 * each a quiet link with the kit's chevron between them, so it reads as a trail and not as
 * words underlined. The page itself is its heading, not a crumb. Named "Breadcrumb", as
 * assistive technology expects.
 */
export function Breadcrumbs({ trail }: { trail: readonly Crumb[] }) {
  if (trail.length === 0) return null;
  return (
    <nav aria-label="Breadcrumb" className={TYPE.meta}>
      <ol className="flex flex-wrap items-center gap-x-(--breadcrumb-gap)">
        {trail.map(({ label, ...to }, at) => (
          <li key={`${at}:${label}`} className="flex items-center gap-x-(--breadcrumb-gap)">
            {at > 0 && <Icon icon={glyphs.chevronRight} className="size-3.5 text-muted" />}
            <CrumbLink {...to}>{label}</CrumbLink>
          </li>
        ))}
      </ol>
    </nav>
  );
}
