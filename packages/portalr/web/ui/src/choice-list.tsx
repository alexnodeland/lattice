import { Radio } from "@base-ui/react/radio";
import { RadioGroup } from "@base-ui/react/radio-group";
import { useId } from "react";
import { cn } from "./cn";
import { MARK, ROW } from "./questions";

/** One of a choice list's options: its value, its name, and what it means in a line. */
export interface ChoiceOption<V extends string> {
  readonly value: V;
  readonly label: string;
  readonly line?: string | undefined;
}

/**
 * A setting chosen among a few, such as in a sheet (portalr ADR-0087): a radio group, each option
 * a row as a question's option is (a mark, its name, its line), named by its name and described by
 * its line; the arrows move and choose, as a radio group's do, and the group is one tab stop. What
 * is chosen takes effect at once: the sheet holding it is closed by its own Close.
 */
export function ChoiceList<V extends string>({
  label,
  value,
  options,
  onChange,
  disabled = false,
}: {
  label: string;
  value: V;
  options: readonly ChoiceOption<V>[];
  onChange: (value: V) => void;
  disabled?: boolean;
}) {
  const id = useId();
  return (
    <RadioGroup
      aria-label={label}
      value={value}
      disabled={disabled}
      onValueChange={(chosen) => onChange(chosen as V)}
      className="flex flex-col gap-1.5 pt-1"
    >
      {options.map((option, at) => (
        <Radio.Root
          key={option.value}
          value={option.value}
          aria-label={option.label}
          {...(option.line && { "aria-describedby": `${id}-${at}` })}
          className={ROW}
        >
          <span className={cn(MARK, "rounded-full")}>
            <Radio.Indicator className="size-2 rounded-full bg-accent" />
          </span>
          <span className="flex min-w-0 flex-col">
            <span className="font-medium">{option.label}</span>
            {option.line && (
              <span id={`${id}-${at}`} className="text-muted text-xs">
                {option.line}
              </span>
            )}
          </span>
        </Radio.Root>
      ))}
    </RadioGroup>
  );
}
