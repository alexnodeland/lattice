import type { LucideIcon } from "lucide-react";
import { cn } from "./cn";

/**
 * A Lucide icon, always beside the word it stands for: hidden from assistive technology, since
 * the word names it, and never a control's only label.
 */
export function Icon({ icon: Glyph, className }: { icon: LucideIcon; className?: string }) {
  return (
    <Glyph
      aria-hidden="true"
      focusable="false"
      size={16}
      strokeWidth={2}
      className={cn("shrink-0", className)}
    />
  );
}
