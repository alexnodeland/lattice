import { Checkbox as BaseCheckbox } from "@base-ui/react/checkbox";
import { CheckboxGroup as BaseCheckboxGroup } from "@base-ui/react/checkbox-group";
import { Field } from "@base-ui/react/field";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";
import { FieldGroup } from "./field-group";
import { Icon } from "./icon";
import { glyphs } from "./icons";
import { FEEDBACK, RING } from "./states";

/** One of a checkbox group's choices: what it submits, and the words beside it. */
export interface CheckboxChoice {
  readonly value: string;
  readonly label: string;
  /** Not to be changed, as it is, where the rest may be. */
  readonly disabled?: boolean;
  /** Said under it, and describing it: such as why it can't be changed. */
  readonly description?: string;
}

/**
 * A box, marked in the working colour when checked: Base UI's checkbox, which a `Field.Label`
 * around it and its words names. Inside a group, its `value` is what the group holds when it is.
 */
export function Checkbox(props: Omit<ComponentProps<typeof BaseCheckbox.Root>, "className">) {
  return (
    <BaseCheckbox.Root
      className={cn(
        "grid size-(--checkbox-size) shrink-0 place-items-center rounded-(--checkbox-radius) border border-edge bg-surface data-checked:border-accent data-checked:bg-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-wash",
        RING,
        FEEDBACK,
      )}
      {...props}
    >
      <BaseCheckbox.Indicator className="text-on-accent">
        <Icon icon={glyphs.check} className="size-3" />
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
            <Field.Root key={choice.value} disabled={choice.disabled}>
              <Field.Label className="flex items-center gap-2 text-fg text-sm data-disabled:text-muted">
                <Checkbox value={choice.value} />
                {choice.label}
              </Field.Label>
              {choice.description && (
                <Field.Description className="ps-(--checkbox-size) ms-2 text-muted text-xs">
                  {choice.description}
                </Field.Description>
              )}
            </Field.Root>
          ))}
        </BaseCheckboxGroup>
      )}
    </FieldGroup>
  );
}
