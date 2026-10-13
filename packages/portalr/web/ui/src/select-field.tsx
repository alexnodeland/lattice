import { type ComponentProps, useId } from "react";
import { cn } from "./cn";

type Props = Omit<ComponentProps<"select">, "className" | "children" | "id"> & {
  label: string;
  /** The choices, each a value and the words it shows as. */
  options: readonly { readonly value: string; readonly label: string }[];
  className?: string;
};

/**
 * A labelled choice among a few, as the platform's own select: it reads and submits as a form's
 * field, and keeps the platform's keyboard and its picker on a phone.
 */
export function SelectField({ label, options, className, ...props }: Props) {
  const id = useId();
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <label htmlFor={id} className="font-semibold text-fg text-sm">
        {label}
      </label>
      <select
        id={id}
        className="rounded-md border border-edge bg-surface px-3 py-1.5 text-fg text-sm outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus disabled:cursor-not-allowed disabled:border-line disabled:bg-paper disabled:text-muted"
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}
