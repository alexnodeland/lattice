import { Button as BaseButton } from "@base-ui/react/button";
import type { ComponentProps } from "react";

const look = {
  primary: "bg-accent text-on-accent hover:opacity-90",
  secondary: "bg-surface text-text border border-line hover:bg-paper",
} as const;

/** A button: Base UI's, in the working colour (`primary`) or on the surface (`secondary`). */
export function Button({
  variant = "primary",
  className,
  ...props
}: ComponentProps<typeof BaseButton> & { variant?: keyof typeof look }) {
  return (
    <BaseButton
      className={`inline-flex items-center gap-2 rounded-md px-3 py-1.5 font-sans text-sm font-semibold outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus data-[disabled]:opacity-50 ${look[variant]} ${className ?? ""}`}
      {...props}
    />
  );
}
