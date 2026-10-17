import { Field } from "@base-ui/react/field";
import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * A form control's frame: its label, the control, a hint under it, and why it was refused. Base
 * UI's Field names the control by its label and describes it by the hint and the error, so a
 * screen reader hears each with it. A field is no wider than `max-w-md`, 28rem, however wide its
 * form is: a control wider than the words it takes is harder to read than to fill.
 */
export function FormField({
  label,
  hint,
  error = null,
  className,
  children,
}: {
  label: string;
  /** What to enter, or what the choices mean, said under the control. */
  hint?: ReactNode;
  /** Why what was entered was refused: it marks the field invalid, and says so beneath it. */
  error?: string | null;
  className?: string | undefined;
  /** The control, such as Base UI's `Field.Control`, or a `Select`. */
  children: ReactNode;
}) {
  return (
    <Field.Root
      className={cn("flex w-full max-w-md flex-col gap-1", className)}
      invalid={error !== null}
    >
      <Field.Label className="font-semibold text-fg text-sm">{label}</Field.Label>
      {children}
      {hint !== undefined && (
        <Field.Description className="text-muted text-xs">{hint}</Field.Description>
      )}
      <Field.Error className="text-fg text-sm" match={error !== null}>
        {error}
      </Field.Error>
    </Field.Root>
  );
}
