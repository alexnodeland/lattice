import { Field } from "@base-ui/react/field";
import type { ComponentProps, ReactNode } from "react";
import { cn } from "./cn";
import { FormField } from "./form-field";
import { control } from "./text-field";

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
        className={cn(control, "min-h-16 resize-y leading-normal data-disabled:resize-none")}
        {...props}
      />
    </FormField>
  );
}
