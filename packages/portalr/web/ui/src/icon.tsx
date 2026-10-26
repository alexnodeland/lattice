import { cn } from "./cn";
import type { Glyph } from "./icons";

/**
 * One of the kit's own icons (`icons.ts`, portalr ADR-0080), always beside the word it stands
 * for: hidden from assistive technology, since the word names it, and never a control's only
 * label. Drawn 16 units across in the text's colour, stroked 1.5 with round terminals;
 * `className` sizes it.
 */
export function Icon({ icon, className }: { icon: Glyph; className?: string }) {
  return (
    <svg
      aria-hidden="true"
      focusable="false"
      // What tells the kit's own drawing from one a message smuggled in (markdown.test.tsx).
      data-glyph=""
      viewBox="0 0 16 16"
      width={16}
      height={16}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn("shrink-0", className)}
    >
      <path d={icon} />
    </svg>
  );
}
