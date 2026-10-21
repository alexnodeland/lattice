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
    "border-transparent bg-transparent text-danger hover:not-data-disabled:bg-danger-wash",
} as const;

const size = {
  md: "px-(--button-pad-x) py-(--button-pad-y) text-sm",
  /** For an action in a row, where the row's own words are the larger. */
  sm: "px-(--button-sm-pad-x) py-(--button-sm-pad-y) text-xs",
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

/** A button's look, for what is drawn as a button but rendered as something else, such as a link. */
export function buttonLook(variant: ButtonVariant = "primary", big: ButtonSize = "md") {
  return cn(
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-(--button-radius) border font-(--button-weight) font-sans outline-offset-(--focus-offset) transition-[color,background-color,border-color] duration-(--button-duration) ease-(--button-ease) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus active:not-data-disabled:translate-y-(--button-press-shift) motion-reduce:transition-none aria-pressed:border-accent aria-pressed:bg-wash aria-pressed:text-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-line data-disabled:text-muted",
    size[big],
    look[variant],
  );
}

/**
 * A button: Base UI's, in the working colour (`primary`), on the surface (`secondary`), bare until
 * hovered (`ghost`), or in the danger colour (`danger-soft` offers a destructive action, `danger`
 * confirms it), in two sizes. A pressed toggle takes the wash. A disabled one is on a muted fill, in
 * the quiet text, with the cursor that says it can't be used, rather than faded, so it still reads.
 */
export function Button({ variant = "primary", size: big = "md", className, ...props }: Props) {
  return <BaseButton className={cn(buttonLook(variant, big), className)} {...props} />;
}
