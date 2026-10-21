import { Checkbox as BaseCheckbox } from "@base-ui/react/checkbox";
import { CheckboxGroup as BaseCheckboxGroup } from "@base-ui/react/checkbox-group";
import { Field } from "@base-ui/react/field";
import { Check } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { FieldGroup } from "./field-group";
import { Icon } from "./icon";

/** One of a checkbox group's choices: what it submits, and the words beside it. */
export interface CheckboxChoice {
  readonly value: string;
  readonly label: string;
}

/**
 * A box, marked in the working colour when checked: Base UI's checkbox, which a `Field.Label`
 * around it and its words names. Inside a group, its `value` is what the group holds when it is.
 */
export function Checkbox(props: Omit<ComponentProps<typeof BaseCheckbox.Root>, "className">) {
  return (
    <BaseCheckbox.Root
      className="grid size-(--checkbox-size) shrink-0 place-items-center rounded-(--checkbox-radius) border border-edge bg-surface outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus data-checked:border-accent data-checked:bg-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-wash"
      {...props}
    >
      <BaseCheckbox.Indicator className="text-on-accent">
        <Icon icon={Check} className="size-3" />
      </BaseCheckbox.Indicator>
    </BaseCheckbox.Root>
  );
}

/**
 * Several choices, any of them checked: Base UI's checkbox group, named by its legend, each box
 * marked in the working colour when checked. Its value is the checked choices' values. A hint
 * under it, and why it was refused, describe the group, as a field's describe its control.
 */
export function CheckboxGroup({
  legend,
  choices,
  value,
  onValueChange,
  hint,
  error = null,
  disabled = false,
}: {
  legend: ReactNode;
  choices: readonly CheckboxChoice[];
  value: readonly string[];
  onValueChange: (value: string[]) => void;
  /** What the choices mean, said under them. */
  hint?: ReactNode;
  /** Why what was checked was refused: it marks the group invalid, and says so beneath it. */
  error?: string | null;
  /** Shown as checked, and not to be changed. */
  disabled?: boolean;
}) {
  return (
    <FieldGroup label={legend} hint={hint} error={error}>
      {(grouped) => (
        <BaseCheckboxGroup
          {...grouped}
          value={[...value]}
          disabled={disabled}
          onValueChange={(chosen) => onValueChange(chosen)}
          className="flex flex-col gap-1.5 pt-1"
        >
          {choices.map((choice) => (
            <Field.Root key={choice.value}>
              <Field.Label className="flex items-center gap-2 text-fg text-sm">
                <Checkbox value={choice.value} />
                {choice.label}
              </Field.Label>
            </Field.Root>
          ))}
        </BaseCheckboxGroup>
      )}
    </FieldGroup>
  );
}
