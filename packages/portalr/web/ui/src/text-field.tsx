import { Field } from "@base-ui/react/field";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";
import { FormField } from "./form-field";
import { FEEDBACK, RING } from "./states";

/** What a field's control shares with a text area's: the kit's edge, its padding, and its states. */
export const control = cn(
  "rounded-(--input-radius) border border-edge bg-surface px-(--input-pad-x) py-(--input-pad-y) text-fg text-sm placeholder:text-muted data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-line data-disabled:text-muted data-invalid:border-status-failed",
  RING,
  FEEDBACK,
);

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
      <Field.Control className={control} {...props} />
    </FormField>
  );
}
