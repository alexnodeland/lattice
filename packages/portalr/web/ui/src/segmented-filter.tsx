import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import type { ReactNode } from "react";
import { cn } from "./cn";
import { FieldGroup, type Grouped } from "./field-group";
import { FEEDBACK, RING } from "./states";

/** One way to filter, with how many it shows, if known. */
export type Segment<V extends string> = {
  readonly value: V;
  readonly label: string;
  readonly count?: number;
};

/**
 * One filter of a few, side by side, such as a window of hours, days or weeks: Base UI's radio
 * group, whose arrow keys move the choice. The track is flat, on the line, and the chosen one is
 * raised on the surface, in the text's weight, where the rest are quiet (portalr ADR-0080). A count is said after its word ("All, 7"). With
 * `showLabel` the group's name is written above it as a field's is, with its `hint` beneath and why
 * the choice was refused, if it was; with `name` it submits with its form.
 */
export function SegmentedFilter<V extends string>({
  name,
  segments,
  value,
  onValueChange,
  disabled = false,
  size = "md",
  ...written
}: {
  name?: string;
  segments: readonly Segment<V>[];
  value: V;
  onValueChange: (value: V) => void;
  /** Shown as chosen, and not to be changed. */
  disabled?: boolean;
  /** `sm` for a setting in a row of controls, such as the composer's (portalr ADR-0085). */
  size?: "md" | "sm";
} & (
  | {
      /** Write the group's name above it, as a field's, with a hint beneath. */
      showLabel: true;
      /** Its name, written: words, or words and a mark such as "required". */
      label: ReactNode;
      hint?: ReactNode;
      /** Why the choice was refused: it marks the group invalid, and says so beneath it. */
      error?: string | null;
    }
  | { showLabel?: false; label: string; hint?: never; error?: never }
)) {
  const group = (named: Grouped | { readonly "aria-label": string }) => (
    <RadioGroup<V>
      {...named}
      {...(name !== undefined && { name })}
      value={value}
      disabled={disabled}
      onValueChange={(chosen) => onValueChange(chosen)}
      className={cn(
        "inline-flex gap-0.5 self-start rounded-(--segmented-radius) border border-line bg-subtle p-(--segmented-pad) aria-invalid:border-status-failed",
        // In a row of controls, one line at its content's width, never squeezed into two.
        size === "sm" ? "shrink-0" : "flex-wrap",
      )}
    >
      {segments.map((segment) => (
        <Radio.Root
          key={segment.value}
          value={segment.value}
          aria-label={
            segment.count === undefined ? undefined : `${segment.label}, ${segment.count}`
          }
          className={cn(
            "inline-flex cursor-default items-center gap-1.5 rounded-(--segmented-item-radius) px-(--segmented-item-pad-x) py-(--segmented-item-pad-y) font-medium text-muted hover:not-data-disabled:text-fg data-checked:bg-surface data-checked:font-semibold data-checked:text-fg data-checked:shadow-(--card-shadow) data-disabled:cursor-not-allowed data-disabled:text-muted",
            size === "sm" ? "text-xs" : "text-sm",
            RING,
            FEEDBACK,
          )}
        >
          {segment.label}
          {/* A count in the sans, on its digits, as every count is (portalr ADR-0085). */}
          {segment.count !== undefined && (
            <span aria-hidden="true" className="font-normal text-xs tabular-nums">
              {segment.count}
            </span>
          )}
        </Radio.Root>
      ))}
    </RadioGroup>
  );
  if (!written.showLabel) {
    return group({ "aria-label": written.label });
  }
  return (
    <FieldGroup label={written.label} hint={written.hint} error={written.error ?? null}>
      {group}
    </FieldGroup>
  );
}
