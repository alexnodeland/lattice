import type { ReactNode } from "react";
import { cn } from "./cn";
import { TYPE } from "./type";

/**
 * The top of a page: where it is, its one heading, a line about it, and its actions, which wrap
 * beneath the heading on a narrow screen.
 */
export function PageHeader({
  title,
  crumb,
  meta,
  actions,
  id,
  mono = false,
}: {
  title: string;
  /** Whether the title is an id, set in the mono face as lists set ids. */
  mono?: boolean;
  /** The heading's id, for a region it names. */
  id?: string;
  /** The way back, such as a link to the area. */
  crumb?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pb-1">
      <div className="flex min-w-0 flex-col gap-1">
        {crumb && <div className={TYPE.note}>{crumb}</div>}
        <h1 id={id} className={cn(TYPE.page, mono && "font-mono")}>
          {title}
        </h1>
        {meta && <p className={TYPE.meta}>{meta}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
