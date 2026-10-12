import { Field } from "@base-ui/react/field";
import type { ComponentProps } from "react";
import { cn } from "./cn";

type Props = Omit<ComponentProps<typeof Field.Control>, "className"> & {
  label: string;
  /** Why what was entered was refused: it marks the field invalid, and says so beneath it. */
  error?: string | null;
  className?: string;
};

/** A labelled text field: Base UI's, whose input names itself by its label. */
export function TextField({ label, error = null, className, ...props }: Props) {
  return (
    <Field.Root className={cn("flex flex-col gap-1", className)} invalid={error !== null}>
      <Field.Label className="font-semibold text-fg text-sm">{label}</Field.Label>
      <Field.Control
        className="rounded-md border border-edge bg-surface px-3 py-1.5 text-fg text-sm outline-offset-2 placeholder:text-muted focus-visible:outline-2 focus-visible:outline-focus data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-paper data-disabled:text-muted data-invalid:border-fg"
        {...props}
      />
      <Field.Error className="text-fg text-sm" match={error !== null}>
        {error}
      </Field.Error>
    </Field.Root>
  );
}
