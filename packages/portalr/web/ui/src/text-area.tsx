import { Field } from "@base-ui/react/field";
import type { ComponentProps, ReactNode } from "react";
import { FormField } from "./form-field";

type Props = Omit<ComponentProps<typeof Field.Control>, "className" | "render"> & {
  label: ReactNode;
  hint?: ReactNode;
  /** Why what was entered was refused: it marks the field invalid, and says so beneath it. */
  error?: string | null;
  /** How many lines it shows before it scrolls: four unless said. */
  rows?: number;
  className?: string;
};

/**
 * A labelled text area, for more than a line: Base UI's field, as `TextField` is, with a textarea
 * for its control, `rows` lines tall, and taller if the person drags it, never wider than its
 * field.
 */
export function TextArea({ label, hint, error = null, rows = 4, className, ...props }: Props) {
  return (
    <FormField label={label} hint={hint} error={error} className={className}>
      <Field.Control
        render={<textarea rows={rows} />}
        className="min-h-16 resize-y rounded-md border border-edge bg-surface px-3 py-1.5 text-fg text-sm leading-normal outline-offset-(--focus-offset) placeholder:text-muted focus-visible:outline-(length:--focus-width) focus-visible:outline-focus data-disabled:cursor-not-allowed data-disabled:resize-none data-disabled:border-line data-disabled:bg-line data-disabled:text-muted data-invalid:border-fg"
        {...props}
      />
    </FormField>
  );
}
