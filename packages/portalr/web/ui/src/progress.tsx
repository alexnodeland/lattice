/**
 * How far something long has gone, such as an upload: a bar, its share in words beside it, and a
 * `progressbar` that names what it measures (portalr ADR-0049). Under forced colours the bar keeps
 * the system's highlight, where the accent's fill would go.
 */

import { cn } from "./cn";

export function Progress({
  label,
  value,
  max,
  valueText,
  className,
}: {
  /** What is going, such as "Checking in brief.docx". */
  label: string;
  value: number;
  max: number;
  /** How far it has gone, in words, such as "21 kB of 48 kB", for assistive technology. */
  valueText?: string;
  className?: string;
}) {
  const share = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className={cn("flex flex-col gap-1 text-sm", className)}>
      <div className="flex justify-between gap-3">
        <span className="text-fg">{label}</span>
        <span aria-hidden="true" className="text-muted tabular-nums">
          {share}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={share}
        aria-valuetext={valueText}
        className="h-(--progress-height) overflow-hidden rounded-(--progress-radius) border border-line bg-paper forced-colors:border-system-text"
      >
        <div
          className="h-full origin-left bg-accent transition-transform duration-(--progress-duration) motion-reduce:transition-none forced-color-adjust-none forced-colors:bg-system-highlight"
          style={{ transform: `scaleX(${share / 100})` }}
        />
      </div>
    </div>
  );
}
