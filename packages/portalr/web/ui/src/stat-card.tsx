import { type ReactNode, useId } from "react";
import { Card } from "./card";

/**
 * One figure, read on its own, as admin's Home shows each: its title, the figure or why there's
 * none, a line about it, and where to go for more. A card that can't read says so, and the others
 * read on.
 */
export function StatCard({
  title,
  figure,
  children,
  action,
}: {
  title: string;
  /** The figure, or null while it's read or when there's none to show. */
  figure: ReactNode;
  /** What the figure is, or why there isn't one. */
  children?: ReactNode;
  /** Where to go for more, such as a link to its area. */
  action?: ReactNode;
}) {
  const heading = useId();
  return (
    <Card render={<section aria-labelledby={heading} />} className="flex flex-col gap-1">
      <h2 id={heading} className="font-semibold text-muted text-sm">
        {title}
      </h2>
      {figure !== null && (
        <p className="font-bold text-2xl text-fg tracking-tight tabular-nums">{figure}</p>
      )}
      {children && <div className="text-muted text-sm">{children}</div>}
      {action && <div className="mt-2 text-sm">{action}</div>}
    </Card>
  );
}
