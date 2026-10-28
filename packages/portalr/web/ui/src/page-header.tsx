import { type ReactNode, useEffect, useRef } from "react";
import { cn } from "./cn";
import { TYPE } from "./type";

/**
 * The top of a page: the places above it, its one heading with its actions on the same line, and
 * a line about it. The actions are few and compact, an icon button where words would crowd.
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
  /**
   * The places above this page, a `Breadcrumbs`: the way back up, where the frame doesn't mark it
   * (the app's bar marks the current area, portalr ADR-0087).
   */
  breadcrumbs?: ReactNode;
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
    // One shape (portalr ADR-0085): the places above, then the title with the actions on its
    // line, at every width, never wrapped under it; then the line about it.
    <header className="flex flex-col gap-1">
      {breadcrumbs}
      <div className="flex items-center justify-between gap-3">
        <h1
          id={id}
          ref={ref}
          tabIndex={focus ? -1 : undefined}
          className={cn(TYPE.page, "min-w-0 break-words", mono && "font-mono")}
        >
          {title}
        </h1>
        {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
      </div>
      {meta && <p className={TYPE.meta}>{meta}</p>}
    </header>
  );
}
