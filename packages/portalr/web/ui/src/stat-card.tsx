import { type ReactNode, useId } from "react";
import { Card } from "./card";

/**
 * One figure, read on its own, as admin's Home shows each: an article of its title, its state
 * as a badge where it has one, the figure or why there's none, a line about it, and where to go
 * for more. A card that can't read says so, and the others read on. While it reads, it's busy.
 */
export function StatCard({
  title,
  figure,
  badge,
  busy = false,
  children,
  action,
}: {
  title: string;
  /** The figure, or null while it's read or when there's none to show. */
  figure: ReactNode;
  /** The card's state, such as a `StatusBadge`, beside its title. */
  badge?: ReactNode;
  /** Whether it's being read. */
  busy?: boolean;
  /** What the figure is, or why there isn't one. */
  children?: ReactNode;
  /** Where to go for more, such as a link to its area. */
  action?: ReactNode;
}) {
  const heading = useId();
  return (
    <Card
      render={<article aria-labelledby={heading} aria-busy={busy} />}
      className="flex flex-col gap-1"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={heading} className="font-semibold text-muted text-sm">
          {title}
        </h2>
        {badge}
      </div>
      {figure !== null && (
        <p className="font-bold text-2xl text-fg tabular-nums tracking-tight">{figure}</p>
      )}
      {children && <div className="text-muted text-sm">{children}</div>}
      {action && <div className="mt-2 text-sm">{action}</div>}
    </Card>
  );
}
