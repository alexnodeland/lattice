import { type ReactNode, useEffect, useId, useRef } from "react";
import { SectionTitle } from "./section-title";

/**
 * Nothing to show, or nothing at this address: a heading saying so, what will be here in a
 * sentence, and the one thing to do about it (portalr ADR-0065). No illustration. A state that
 * stands in for the page the reader asked for, such as one not found, takes `focus`, so its
 * heading is where the keyboard and a screen reader land.
 */
export function EmptyState({
  title,
  children,
  action,
  focus = false,
}: {
  title: string;
  /** What will appear, and when. */
  children: ReactNode;
  /** The one thing to do, such as a link to start. */
  action?: ReactNode;
  /** Move the focus to the heading when it appears, for a state that replaces the page. */
  focus?: boolean;
}) {
  const heading = useId();
  const ref = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (focus) {
      ref.current?.focus();
    }
  }, [focus]);
  return (
    <section
      aria-labelledby={heading}
      className="flex max-w-xl flex-col items-center gap-2 rounded-(--card-radius) border border-line border-dashed p-(--empty-state-pad) text-center"
    >
      <SectionTitle id={heading} ref={ref} tabIndex={focus ? -1 : undefined}>
        {title}
      </SectionTitle>
      <div className="text-muted text-sm">{children}</div>
      {action && <div className="pt-1">{action}</div>}
    </section>
  );
}
