import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { type ReactNode, useId } from "react";

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
 * `showLabel` the group's name is written above it as a field's is, with its `hint` beneath; with
 * `name` it submits with its form.
 */
export function SegmentedFilter<V extends string>({
  label,
  name,
  segments,
  value,
  onValueChange,
  ...written
}: {
  label: string;
  name?: string;
  segments: readonly Segment<V>[];
  value: V;
  onValueChange: (value: V) => void;
} & (
  | {
      /** Write the group's name above it, as a field's, with a hint beneath. */
      showLabel: true;
      hint?: ReactNode;
    }
  | { showLabel?: false; hint?: never }
)) {
  const labelId = useId();
  const hintId = useId();
  const showLabel = written.showLabel === true;
  const hint = written.showLabel ? written.hint : undefined;
  const group = (
    <RadioGroup<V>
      {...(showLabel ? { "aria-labelledby": labelId } : { "aria-label": label })}
      {...(hint !== undefined && { "aria-describedby": hintId })}
      {...(name !== undefined && { name })}
      value={value}
      onValueChange={(chosen) => onValueChange(chosen)}
      className="inline-flex flex-wrap gap-0.5 self-start rounded-md border border-edge bg-surface p-0.5"
    >
      {segments.map((segment) => (
        <Radio.Root
          key={segment.value}
          value={segment.value}
          aria-label={
            segment.count === undefined ? undefined : `${segment.label}, ${segment.count}`
          }
          className="inline-flex cursor-default items-center gap-1.5 rounded border border-transparent px-2.5 py-1 font-medium text-fg text-sm outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus data-checked:border-accent data-checked:bg-wash data-checked:font-semibold data-checked:text-accent"
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
  if (!showLabel) {
    return group;
  }
  return (
    <div className="flex flex-col gap-1">
      <span id={labelId} className="font-semibold text-fg text-sm">
        {label}
      </span>
      {group}
      {hint !== undefined && (
        <p id={hintId} className="text-muted text-xs">
          {hint}
        </p>
      )}
    </div>
  );
}
