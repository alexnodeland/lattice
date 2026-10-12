import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";

/** One way to filter, with how many it shows, if known. */
export type Segment<V extends string> = {
  readonly value: V;
  readonly label: string;
  readonly count?: number;
};

/**
 * One filter of a few, side by side: Base UI's radio group, whose arrow keys move the choice. The
 * chosen one is pressed as every chosen control is, on the wash, in the working colour, edged in
 * it. A count is said after its word ("All, 7").
 */
export function SegmentedFilter<V extends string>({
  label,
  segments,
  value,
  onValueChange,
}: {
  label: string;
  segments: readonly Segment<V>[];
  value: V;
  onValueChange: (value: V) => void;
}) {
  return (
    <RadioGroup<V>
      aria-label={label}
      value={value}
      onValueChange={(chosen) => onValueChange(chosen)}
      className="inline-flex gap-0.5 rounded-md border border-edge bg-surface p-0.5"
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
}
