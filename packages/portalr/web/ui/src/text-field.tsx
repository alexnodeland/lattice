import { Field } from "@base-ui/react/field";
import type { ComponentProps } from "react";
import { cn } from "./cn";

type Props = Omit<ComponentProps<typeof Field.Control>, "className"> & {
  label: string;
  className?: string;
};

/** A labelled text field: Base UI's, whose input names itself by its label. */
export function TextField({ label, className, ...props }: Props) {
  return (
    <Field.Root className={cn("flex flex-col gap-1", className)}>
      <Field.Label className="font-semibold text-fg text-sm">{label}</Field.Label>
      <Field.Control
        className="rounded-md border border-line bg-surface px-3 py-1.5 text-fg text-sm outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50"
        {...props}
      />
    </Field.Root>
  );
}
