import { Checkbox } from "@base-ui/react/checkbox";
import { CheckboxGroup as BaseCheckboxGroup } from "@base-ui/react/checkbox-group";
import { Field } from "@base-ui/react/field";
import { Check } from "lucide-react";
import { useId } from "react";
import { Icon } from "./icon";

/** One of a checkbox group's choices: what it submits, and the words beside it. */
export interface CheckboxChoice {
  readonly value: string;
  readonly label: string;
}

/**
 * Several choices, any of them checked: Base UI's checkbox group, named by its legend, each box
 * marked in the working colour when checked. Its value is the checked choices' values.
 */
export function CheckboxGroup({
  legend,
  choices,
  value,
  onValueChange,
}: {
  legend: string;
  choices: readonly CheckboxChoice[];
  value: readonly string[];
  onValueChange: (value: string[]) => void;
}) {
  const named = useId();
  return (
    <BaseCheckboxGroup
      aria-labelledby={named}
      value={[...value]}
      onValueChange={(chosen) => onValueChange(chosen)}
      className="flex flex-col gap-1.5"
    >
      <span id={named} className="mb-1 font-semibold text-fg text-sm">
        {legend}
      </span>
      {choices.map((choice) => (
        <Field.Root key={choice.value}>
          <Field.Label className="flex items-center gap-2 text-fg text-sm">
            <Checkbox.Root
              value={choice.value}
              className="grid size-4 place-items-center rounded border border-edge bg-surface outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus data-checked:border-accent data-checked:bg-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-wash"
            >
              <Checkbox.Indicator className="text-on-accent">
                <Icon icon={Check} className="size-3" />
              </Checkbox.Indicator>
            </Checkbox.Root>
            {choice.label}
          </Field.Label>
        </Field.Root>
      ))}
    </BaseCheckboxGroup>
  );
}
