import { Button as BaseButton } from "@base-ui/react/button";
import type { ComponentProps } from "react";
import { cn } from "./cn";

const look = {
  primary: "border-transparent bg-accent text-on-accent hover:not-data-disabled:bg-accent-hover",
  secondary: "border-edge bg-surface text-fg hover:not-data-disabled:bg-wash",
  ghost: "border-transparent bg-transparent text-fg hover:not-data-disabled:bg-wash",
} as const;

type Props = Omit<ComponentProps<typeof BaseButton>, "className"> & {
  variant?: keyof typeof look;
  className?: string;
};

/**
 * A button: Base UI's, in the working colour (`primary`), on the surface (`secondary`), or bare
 * until hovered (`ghost`). A pressed toggle takes the wash; a disabled one keeps its words
 * readable in the quiet text, with no fill, rather than fading.
 */
export function Button({ variant = "primary", className, ...props }: Props) {
  return (
    <BaseButton
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border px-3 py-1.5 font-sans font-semibold text-sm outline-offset-2 transition-[color,background-color,border-color] focus-visible:outline-2 focus-visible:outline-focus active:not-data-disabled:translate-y-px motion-reduce:transition-none aria-pressed:border-accent aria-pressed:bg-wash aria-pressed:text-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-transparent data-disabled:text-muted",
        look[variant],
        className,
      )}
      {...props}
    />
  );
}
