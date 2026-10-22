import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * How a thing is going, as a shape and a word, never colour alone. The word is always in the
 * ink, which reads on the pill; the colour is the border and the shape, as a mark. Only waiting
 * for you takes the working colour. What failed, and a budget overspent, are edged in the rose
 * red; what is retrying, and a budget nearly spent, in the gold; the rest are neutral
 * (portalr ADR-0039). Under forced colours the shapes keep their own colours, as the border would not be
 * enough to tell them by. A budget nearly spent is a half-filled ring, and one overspent a triangle.
 */
const TONE = {
  working: {
    badge: "border-line bg-surface text-fg",
    glyph:
      "rounded-full border-2 border-current border-r-transparent animate-spin [animation-play-state:var(--motion-loop)] motion-reduce:animate-none",
  },
  waiting: {
    badge: "border-accent bg-accent text-on-accent",
    // On the accent's fill, the ink's colour; under forced colours, where the fill goes, the text's.
    glyph: "rotate-45 scale-75 bg-current forced-colors:bg-system-text",
  },
  done: { badge: "border-line bg-surface text-muted", glyph: "rounded-full bg-current" },
  failed: { badge: "border-status-failed bg-surface text-fg", glyph: "bg-status-failed" },
  retrying: {
    badge: "border-status-warn bg-surface text-fg",
    glyph: "rotate-45 scale-75 border-2 border-status-warn",
  },
  queued: {
    badge: "border-line bg-surface text-muted",
    glyph: "rounded-full border-2 border-dotted border-current",
  },
  stopped: { badge: "border-line bg-surface text-muted", glyph: "border-2 border-current" },
  near: {
    badge: "border-status-warn bg-surface text-fg",
    glyph:
      "rounded-full border-2 border-status-warn bg-[linear-gradient(to_top,var(--status-warn)_50%,transparent_50%)]",
  },
  over: {
    badge: "border-status-failed bg-surface text-fg",
    glyph: "bg-status-failed [clip-path:polygon(50%_0,100%_100%,0_100%)]",
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
      // What the style census counts a badge by (portalr ADR-0066).
      data-badge=""
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-(--badge-radius) border py-(--badge-pad-y) pr-(--badge-pad-end) pl-(--badge-pad-start) font-semibold text-xs",
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
