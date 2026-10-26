import { Field } from "@base-ui/react/field";
import { CircleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "./cn";
import { Icon } from "./icon";
import { TYPE } from "./type";

/**
 * Why a field or a group was refused: its words, in the ink, after the failed mark, as an alert's
 * are (portalr ADR-0079). The mark says it to a reader who doesn't follow the control's edge.
 */
export const refusal = "flex items-start gap-1.5 text-fg text-sm";

/** The failed mark before a refusal's words, on their first line. */
export function RefusalMark() {
  return <Icon icon={CircleAlert} className="mt-0.5 text-status-failed" />;
}

/**
 * A form control's frame: its label, the control, a hint under it, and why it was refused. Base
 * UI's Field names the control by its label and describes it by the hint and the error, so a
 * screen reader hears each with it. A field is no wider than `max-w-md`, 28rem, however wide its
 * form is: a control wider than the words it takes is harder to read than to fill. A switch or a
 * box goes `beside` its label.
 */
export function FormField({
  label,
  hint,
  error = null,
  beside = false,
  className,
  children,
}: {
  /** What the field is, which names its control: words, or words and a mark such as "required". */
  label: ReactNode;
  /** What to enter, or what the choices mean, said under the control. */
  hint?: ReactNode;
  /** Why what was entered was refused: it marks the field invalid, and says so beneath it. */
  error?: string | null;
  /** Put the control before its label, on one line, as a switch or a box is. */
  beside?: boolean;
  className?: string | undefined;
  /** The control, such as Base UI's `Field.Control`, or a `Select`. */
  children: ReactNode;
}) {
  return (
    <Field.Root
      className={cn("flex w-full max-w-md flex-col gap-1", className)}
      invalid={error !== null}
    >
      {beside ? (
        <Field.Label className={cn(TYPE.label, "flex items-center gap-2")}>
          {children}
          <span>{label}</span>
        </Field.Label>
      ) : (
        <>
          <Field.Label className={TYPE.label}>{label}</Field.Label>
          {children}
        </>
      )}
      {hint !== undefined && <Field.Description className={TYPE.note}>{hint}</Field.Description>}
      <Field.Error className={refusal} match={error !== null}>
        <RefusalMark />
        <span>{error}</span>
      </Field.Error>
    </Field.Root>
  );
}
