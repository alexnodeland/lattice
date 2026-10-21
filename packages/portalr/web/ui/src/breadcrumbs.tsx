import type { ReactElement } from "react";
import { TextLink } from "./text-link";
import { TYPE } from "./type";

/** One place above this one: its name, and the link to it, such as the router's own. */
export type Crumb = { label: string } & ({ render: ReactElement } | { href: string });

/**
 * The way back up (portalr ADR-0058): the places above this page, outermost first, each a quiet
 * link 24px tall or more, so it is a target on a phone. The page itself is its heading, not a
 * crumb. Named "Breadcrumb", as assistive technology expects.
 */
export function Breadcrumbs({ trail }: { trail: readonly Crumb[] }) {
  return (
    <nav aria-label="Breadcrumb" className={TYPE.meta}>
      <ol className="flex flex-wrap items-center gap-x-(--breadcrumb-gap)">
        {trail.map(({ label, ...to }, at) => (
          <li key={label} className="flex items-center gap-x-(--breadcrumb-gap)">
            {at > 0 && <span aria-hidden="true">/</span>}
            <TextLink
              variant="subtle"
              className="inline-flex min-h-(--breadcrumb-target) items-center"
              {...to}
            >
              {label}
            </TextLink>
          </li>
        ))}
      </ol>
    </nav>
  );
}
