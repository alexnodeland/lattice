import { Field } from "@base-ui/react/field";
import type { ComponentProps, ReactNode } from "react";
import { FormField } from "./form-field";

type Props = Omit<ComponentProps<typeof Field.Control>, "className"> & {
  label: ReactNode;
  hint?: ReactNode;
  /** Why what was entered was refused: it marks the field invalid, and says so beneath it. */
  error?: string | null;
  className?: string;
};

/** A labelled text field: Base UI's, whose input names itself by its label. */
export function TextField({ label, hint, error = null, className, ...props }: Props) {
  return (
    <FormField label={label} hint={hint} error={error} className={className}>
      <Field.Control
        className="rounded-md border border-edge bg-surface px-3 py-1.5 text-fg text-sm outline-offset-2 placeholder:text-muted focus-visible:outline-2 focus-visible:outline-focus data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-line data-disabled:text-muted data-invalid:border-fg"
        {...props}
      />
    </FormField>
  );
}
