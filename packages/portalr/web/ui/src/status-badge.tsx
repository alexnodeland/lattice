import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * How a thing is going, as a shape and a word, never colour alone, with no box (portalr ADR-0039,
 * ADR-0081). The word is in the ink, or the muted for what is over; the colour is the shape's
 * alone, as a mark. Only waiting for you takes the working colour, for its word too.
 * What failed, and a budget overspent, carry the rose red; what is retrying, and a budget nearly
 * spent, the gold; the rest are neutral. Under forced colours the shapes keep their own colours.
 * A budget nearly spent is a half-filled ring, and one overspent a triangle.
 */
const QUIET = "text-fg";
const STILL = "text-muted";

const TONE = {
  working: {
    badge: QUIET,
    glyph:
      // Turning; where motion is reduced, a whole ring, never a still arc that reads as a "c".
      "rounded-full border-2 border-current border-r-transparent animate-spin [animation-play-state:var(--motion-loop)] motion-reduce:animate-none motion-reduce:border-r-current",
  },
  waiting: {
    badge: "text-accent",
    // The working colour; under forced colours, where the wash goes, the text's.
    glyph: "rotate-45 scale-75 bg-current forced-colors:bg-system-text",
  },
  done: { badge: STILL, glyph: "rounded-full bg-current" },
  failed: { badge: QUIET, glyph: "bg-status-failed" },
  retrying: { badge: QUIET, glyph: "rotate-45 scale-75 border-2 border-status-warn" },
  queued: { badge: STILL, glyph: "rounded-full border-2 border-dotted border-current" },
  stopped: { badge: STILL, glyph: "border-2 border-current" },
  near: {
    badge: QUIET,
    glyph:
      "rounded-full border-2 border-status-warn bg-[linear-gradient(to_top,var(--status-warn)_50%,transparent_50%)]",
  },
  over: { badge: QUIET, glyph: "bg-status-failed [clip-path:polygon(50%_0,100%_100%,0_100%)]" },
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

/** A status: its shape and its word, in a badge. */
export function StatusBadge({ tone, children, live = false, className }: Props) {
  return (
    <span
      role={live ? "status" : undefined}
      // What the style census counts a badge by (portalr ADR-0066).
      data-badge=""
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap font-medium text-xs",
        TONE[tone].badge,
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cn("size-2 shrink-0 forced-color-adjust-none", TONE[tone].glyph)}
      />
      {children}
    </span>
  );
}
