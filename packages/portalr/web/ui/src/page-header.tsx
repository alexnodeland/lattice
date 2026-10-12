import type { ReactNode } from "react";

/**
 * The top of a page: where it is, its one heading, a line about it, and its actions, which wrap
 * beneath the heading on a narrow screen.
 */
export function PageHeader({
  title,
  crumb,
  meta,
  actions,
}: {
  title: string;
  /** The way back, such as a link to the area. */
  crumb?: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
      <div className="flex min-w-0 flex-col gap-1">
        {crumb && <div className="text-muted text-xs">{crumb}</div>}
        <h1 className="font-bold text-2xl text-fg tracking-tight">{title}</h1>
        {meta && <p className="text-muted text-xs">{meta}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
