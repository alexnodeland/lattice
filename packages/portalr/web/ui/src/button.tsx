import { Button as BaseButton } from "@base-ui/react/button";
import type { ComponentProps } from "react";
import { cn } from "./cn";

const look = {
  primary: "border-transparent bg-accent text-on-accent hover:not-data-disabled:bg-accent-hover",
  secondary: "border-edge bg-surface text-fg hover:not-data-disabled:bg-wash",
  ghost: "border-transparent bg-transparent text-fg hover:not-data-disabled:bg-wash",
  /** A destructive action's confirmation: the danger colour, solid. */
  danger: "border-transparent bg-danger text-on-danger hover:not-data-disabled:bg-danger-hover",
  /** A destructive action offered, not yet confirmed: the danger colour as words, bare until hovered, then tinted with it. */
  "danger-soft":
    "border-transparent bg-transparent text-danger hover:not-data-disabled:bg-[color-mix(in_srgb,var(--danger)_12%,transparent)]",
} as const;

const size = {
  md: "px-3 py-1.5 text-sm",
  /** For an action in a row, where the row's own words are the larger. */
  sm: "px-2 py-1 text-xs",
} as const;

/** The variants a button comes in. */
export type ButtonVariant = keyof typeof look;
/** The sizes a button comes in. */
export type ButtonSize = keyof typeof size;

type Props = Omit<ComponentProps<typeof BaseButton>, "className"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  className?: string;
};

/**
 * A button: Base UI's, in the working colour (`primary`), on the surface (`secondary`), bare until
 * hovered (`ghost`), or in the danger colour (`danger-soft` offers a destructive action, `danger`
 * confirms it), in two sizes. A pressed toggle takes the wash. A disabled one is on a muted fill, in
 * the quiet text, with the cursor that says it can't be used, rather than faded, so it still reads.
 */
export function Button({ variant = "primary", size: big = "md", className, ...props }: Props) {
  return (
    <BaseButton
      className={cn(
        "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md border font-sans font-semibold outline-offset-2 transition-[color,background-color,border-color] focus-visible:outline-2 focus-visible:outline-focus active:not-data-disabled:translate-y-px motion-reduce:transition-none aria-pressed:border-accent aria-pressed:bg-wash aria-pressed:text-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-line data-disabled:text-muted",
        size[big],
        look[variant],
        className,
      )}
      {...props}
    />
  );
}
