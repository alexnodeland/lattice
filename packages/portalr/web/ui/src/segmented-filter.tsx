import { Toggle } from "@base-ui/react/toggle";
import { ToggleGroup } from "@base-ui/react/toggle-group";

/** One way to filter, with how many it shows, if known. */
export type Segment<V extends string> = {
  readonly value: V;
  readonly label: string;
  readonly count?: number;
};

/**
 * A choice of one filter from a few, side by side: Base UI's toggle group, whose arrow keys move
 * between them. Pressing the chosen one again keeps it chosen.
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
    <ToggleGroup<V>
      aria-label={label}
      value={[value]}
      onValueChange={([chosen]) => {
        if (chosen !== undefined) {
          onValueChange(chosen);
        }
      }}
      className="inline-flex gap-0.5 rounded-md border border-edge bg-surface p-0.5"
    >
      {segments.map((segment) => (
        <Toggle
          key={segment.value}
          value={segment.value}
          className="inline-flex items-center gap-1.5 rounded px-2.5 py-1 font-medium text-fg text-sm outline-offset-2 hover:bg-wash focus-visible:outline-2 focus-visible:outline-focus data-pressed:bg-accent data-pressed:font-semibold data-pressed:text-on-accent"
        >
          {segment.label}
          {segment.count !== undefined && (
            <span className="font-normal text-xs">{segment.count}</span>
          )}
        </Toggle>
      ))}
    </ToggleGroup>
  );
}
