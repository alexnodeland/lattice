import type { ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";
import { glyphs } from "./icons";

/**
 * What an alert is: how it is announced, and its one mark, a shape in its colour (portalr ADR-0085:
 * one signal, not a shape and an edge); the words stay in the ink, which reads on the surface, so
 * no tone depends on its colour. An error interrupts a screen reader (`alert`); a note and a warning wait their turn
 * (`status`).
 */
const TONE = {
  info: { role: "status", icon: glyphs.info, mark: "text-muted" },
  warn: { role: "status", icon: glyphs.triangleAlert, mark: "text-status-warn" },
  error: { role: "alert", icon: glyphs.circleAlert, mark: "text-status-failed" },
} as const;

export type AlertTone = keyof typeof TONE;

/**
 * Something to tell the reader in the page, not a toast: a note, a warning, or what went wrong,
 * with a shape beside its words (portalr ADR-0039). Keep it to a sentence or two, and say what to
 * do. It is a live region, so a change to it is read aloud as the tone says; one that is part
 * of what a page reads, such as a callout in a message, is `live={false}`, a note instead.
 */
export function Alert({
  tone = "info",
  live = true,
  className,
  children,
}: {
  tone?: AlertTone;
  live?: boolean;
  className?: string;
  children: ReactNode;
}) {
  const { role, icon, mark } = TONE[tone];
  return (
    <div
      role={live ? role : "note"}
      className={cn(
        "flex items-start gap-2 rounded-(--alert-radius) border border-line bg-surface px-(--alert-pad-x) py-(--alert-pad-y) text-fg text-sm",
        className,
      )}
    >
      <Icon icon={icon} className={cn("mt-0.5 shrink-0", mark)} />
      <div className="min-w-0">{children}</div>
    </div>
  );
}
