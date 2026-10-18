import { type ReactNode, useId } from "react";

/** What names, describes and marks a group of controls, for the element that is the group. */
export interface Grouped {
  readonly "aria-labelledby": string;
  readonly "aria-describedby"?: string;
  readonly "aria-invalid"?: true;
}

/**
 * A group of controls framed as one field is, such as checkboxes or segments: its name written
 * above it, a hint under it, and why it was refused, each naming or describing the group, which
 * the refusal marks invalid. `children` draws the group, given what it is named and described by.
 */
export function FieldGroup({
  label,
  hint,
  error = null,
  children,
}: {
  /** Its name: words, or words and a mark such as "required". */
  label: ReactNode;
  /** What the choices mean, said under them. */
  hint?: ReactNode;
  /** Why the choice was refused: it marks the group invalid, and says so beneath it. */
  error?: string | null;
  children: (grouped: Grouped) => ReactNode;
}) {
  const labelId = useId();
  const hintId = useId();
  const errorId = useId();
  const described = [hint !== undefined && hintId, error !== null && errorId].filter(Boolean);
  return (
    <div className="flex flex-col gap-1">
      <span id={labelId} className="font-semibold text-fg text-sm">
        {label}
      </span>
      {children({
        "aria-labelledby": labelId,
        ...(described.length > 0 && { "aria-describedby": described.join(" ") }),
        ...(error !== null && { "aria-invalid": true }),
      })}
      {hint !== undefined && (
        <p id={hintId} className="text-muted text-xs">
          {hint}
        </p>
      )}
      {error !== null && (
        <p id={errorId} className="text-fg text-sm">
          {error}
        </p>
      )}
    </div>
  );
}
