import { type ReactNode, useId } from "react";
import { SectionTitle } from "./section-title";

/** Nothing to show yet: what will be here, in a sentence, and the one thing to do about it. */
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string;
  /** What will appear, and when. */
  children: ReactNode;
  /** The one thing to do, such as a link to start. */
  action?: ReactNode;
}) {
  const heading = useId();
  return (
    <section
      aria-labelledby={heading}
      className="flex max-w-xl flex-col items-start gap-3 rounded-lg border border-line bg-surface p-8"
    >
      <SectionTitle id={heading}>{title}</SectionTitle>
      <div className="text-base text-muted">{children}</div>
      {action}
    </section>
  );
}
