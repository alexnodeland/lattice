import { type ReactNode, useEffect, useRef } from "react";
import { Breadcrumbs, type Crumb } from "./breadcrumbs";
import { cn } from "./cn";
import { TYPE } from "./type";

/**
 * The top of a page: the places above it, its one heading, a line about it, and its actions, which wrap
 * beneath the heading on a narrow screen.
 */
export function PageHeader({
  title,
  breadcrumbs,
  meta,
  actions,
  id,
  mono = false,
  focus = false,
}: {
  title: string;
  /** Whether the title is an id, set in the mono face as lists set ids. */
  mono?: boolean;
  /** The heading's id, for a region it names. */
  id?: string;
  /** The places above this page, outermost first: the way back up. */
  breadcrumbs?: readonly Crumb[];
  meta?: ReactNode;
  actions?: ReactNode;
  /**
   * Move the focus to the heading when the page appears, so a reader who followed a link inside
   * the app starts at its top rather than nowhere.
   */
  focus?: boolean;
}) {
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focus) {
      ref.current?.focus();
    }
  }, [focus]);
  return (
    <header className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3 pb-1">
      <div className="flex min-w-0 flex-col gap-1">
        {breadcrumbs && breadcrumbs.length > 0 && <Breadcrumbs trail={breadcrumbs} />}
        <h1
          id={id}
          ref={ref}
          tabIndex={focus ? -1 : undefined}
          className={cn(TYPE.page, mono && "font-mono")}
        >
          {title}
        </h1>
        {meta && <p className={TYPE.meta}>{meta}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
