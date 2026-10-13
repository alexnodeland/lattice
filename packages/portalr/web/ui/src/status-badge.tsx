import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * How a thing is going, as a shape and a word, never colour alone. Only waiting for you takes the
 * working colour; the rest are neutral. A budget nearly spent is a half-filled ring, and one
 * overspent a triangle on the foreground, louder by weight, with no warning colour.
 */
const TONE = {
  working: {
    badge: "border-line bg-surface text-fg",
    glyph:
      "rounded-full border-2 border-current border-r-transparent animate-spin motion-reduce:animate-none",
  },
  waiting: {
    badge: "border-accent bg-accent text-on-accent",
    glyph: "rotate-45 scale-75 bg-current",
  },
  done: { badge: "border-line bg-surface text-muted", glyph: "rounded-full bg-current" },
  failed: { badge: "border-fg bg-surface text-fg", glyph: "bg-current" },
  queued: {
    badge: "border-line bg-surface text-muted",
    glyph: "rounded-full border-2 border-dotted border-current",
  },
  stopped: { badge: "border-line bg-surface text-muted", glyph: "border-2 border-current" },
  near: {
    badge: "border-fg bg-surface text-fg",
    glyph:
      "rounded-full border-2 border-current bg-[linear-gradient(to_top,currentColor_50%,transparent_50%)]",
  },
  over: {
    badge: "border-fg bg-fg text-paper",
    glyph: "bg-current [clip-path:polygon(50%_0,100%_100%,0_100%)]",
  },
} as const;

export type Tone = keyof typeof TONE;

type Props = {
  tone: Tone;
  /** The word. */
  children: ReactNode;
  /** Whether a change is announced, as a status. */
  live?: boolean;
  className?: string;
};

/** A status: its shape and its word, in a pill. */
export function StatusBadge({ tone, children, live = false, className }: Props) {
  return (
    <span
      role={live ? "status" : undefined}
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border py-0.5 pr-2 pl-1.5 font-semibold text-xs",
        TONE[tone].badge,
        className,
      )}
    >
      <span aria-hidden="true" className={cn("size-2 shrink-0", TONE[tone].glyph)} />
      {children}
    </span>
  );
}
