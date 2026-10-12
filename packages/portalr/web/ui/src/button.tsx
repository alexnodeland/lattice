import { Button as BaseButton } from "@base-ui/react/button";
import type { ComponentProps } from "react";
import { cn } from "./cn";

const look = {
  primary: "bg-accent text-on-accent hover:opacity-90",
  secondary: "border border-line bg-surface text-fg hover:bg-paper",
} as const;

type Props = Omit<ComponentProps<typeof BaseButton>, "className"> & {
  variant?: keyof typeof look;
  className?: string;
};

/** A button: Base UI's, in the working colour (`primary`) or on the surface (`secondary`). */
export function Button({ variant = "primary", className, ...props }: Props) {
  return (
    <BaseButton
      className={cn(
        "inline-flex items-center gap-2 rounded-md px-3 py-1.5 font-sans font-semibold text-sm outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
        look[variant],
        className,
      )}
      {...props}
    />
  );
}
