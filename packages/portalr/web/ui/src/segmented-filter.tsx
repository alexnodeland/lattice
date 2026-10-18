import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import type { ReactNode } from "react";
import { FieldGroup, type Grouped } from "./field-group";

/** One way to filter, with how many it shows, if known. */
export type Segment<V extends string> = {
  readonly value: V;
  readonly label: string;
  readonly count?: number;
};

/**
 * One filter of a few, side by side, such as a window of hours, days or weeks: Base UI's radio
 * group, whose arrow keys move the choice. The chosen one is pressed as every chosen control is, on
 * the wash, in the working colour, edged in it. A count is said after its word ("All, 7"). With
 * `showLabel` the group's name is written above it as a field's is, with its `hint` beneath and why
 * the choice was refused, if it was; with `name` it submits with its form.
 */
export function SegmentedFilter<V extends string>({
  name,
  segments,
  value,
  onValueChange,
  disabled = false,
  ...written
}: {
  name?: string;
  segments: readonly Segment<V>[];
  value: V;
  onValueChange: (value: V) => void;
  /** Shown as chosen, and not to be changed. */
  disabled?: boolean;
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
      className="inline-flex flex-wrap gap-0.5 self-start rounded-md border border-edge bg-surface p-0.5 aria-invalid:border-fg"
    >
      {segments.map((segment) => (
        <Radio.Root
          key={segment.value}
          value={segment.value}
          aria-label={
            segment.count === undefined ? undefined : `${segment.label}, ${segment.count}`
          }
          className="inline-flex cursor-default items-center gap-1.5 rounded border border-transparent px-2.5 py-1 font-medium text-fg text-sm outline-offset-2 hover:not-data-disabled:bg-wash focus-visible:outline-2 focus-visible:outline-focus data-checked:border-accent data-checked:bg-wash data-checked:font-semibold data-checked:text-accent data-disabled:cursor-not-allowed data-disabled:text-muted data-checked:data-disabled:border-line data-checked:data-disabled:text-fg"
        >
          {segment.label}
          {segment.count !== undefined && (
            <span aria-hidden="true" className="font-normal text-xs">
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
