import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * A word in a pill that says what something is, not how it is going (that is `StatusBadge`'s):
 * "Latest", "Recommended". Its corners and padding are the badge's tokens, its words always in a
 * colour that reads on its fill (portalr ADR-0062). `neutral` is quiet, on the surface; `accent`
 * is the working colour, for the one thing the reader is pointed to.
 */
const TONE = {
  neutral: "border-line bg-surface text-muted",
  accent: "border-accent bg-accent text-on-accent",
} as const;

export function Badge({
  tone = "neutral",
  id,
  children,
}: {
  tone?: keyof typeof TONE;
  /** For an element it describes. */
  id?: string;
  children: ReactNode;
}) {
  return (
    <span
      id={id}
      className={cn(
        "inline-flex items-center whitespace-nowrap rounded-(--badge-radius) border px-(--badge-pad-end) py-(--badge-pad-y) font-semibold text-xs",
        TONE[tone],
      )}
    >
      {children}
    </span>
  );
}
