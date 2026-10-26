import { Button as BaseButton } from "@base-ui/react/button";
import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement } from "react";
import { cn } from "./cn";
import { RING } from "./states";

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
  /**
   * Whether what it started is still going (portalr ADR-0079): it can't be pressed again, in the
   * disabled look, but keeps the focus it was pressed with, so the keyboard isn't dropped at the
   * document while the command is in flight.
   */
  pending?: boolean;
  className?: string;
};

/** A button's look, for what is drawn as a button but rendered as something else, such as a link. */
export function buttonLook(variant: ButtonVariant = "primary", big: ButtonSize = "md") {
  return cn(
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-(--button-radius) border font-(--button-weight) font-sans transition-[color,background-color,border-color] duration-(--button-duration) ease-(--button-ease) active:not-data-disabled:translate-y-(--button-press-shift) motion-reduce:transition-none aria-pressed:border-accent aria-pressed:bg-wash aria-pressed:text-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-line data-disabled:text-muted",
    RING,
    size[big],
    look[variant],
  );
}

/**
 * A button: Base UI's, in the working colour (`primary`), on the surface (`secondary`), bare until
 * hovered (`ghost`), or in the danger colour (`danger-soft` offers a destructive action, `danger`
 * confirms it), in two sizes. A pressed toggle takes the wash. A disabled one is on a muted fill, in
 * the quiet text, with the cursor that says it can't be used, rather than faded, so it still reads;
 * one that is `pending` looks the same and keeps the focus.
 */
export function Button({
  variant = "primary",
  size: big = "md",
  pending = false,
  disabled = false,
  focusableWhenDisabled = false,
  className,
  ...props
}: Props) {
  return (
    <BaseButton
      className={cn(buttonLook(variant, big), className)}
      disabled={disabled || pending}
      focusableWhenDisabled={focusableWhenDisabled || pending}
      {...props}
    />
  );
}

/**
 * A link in a button's look (portalr ADR-0080): a way on that is an action, such as "All threads"
 * under a not-found or "Start again" on a plain page. It stays a link, the router's through
 * `render` or an `<a>`, so it opens in a new tab, Enter follows it and Space doesn't, and a
 * screen reader hears a link; it has no disabled state, as a link hasn't. Where the router marks
 * it the current page (`aria-current="page"`), it is the text's weight with the nav's rule at
 * its start, so the current place is told by more than colour. The census counts it with the
 * buttons (`data-button`).
 */
export function ButtonLink({
  variant = "secondary",
  size: big = "md",
  render,
  className,
  ...props
}: Omit<ComponentProps<"a">, "className"> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  /** What to render as the link, such as the router's own: an `<a>` without one. */
  render?: ReactElement;
  className?: string;
}) {
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      // What the style census counts a button by, as a link (`data-*` is past the anchor's type).
      {
        "data-button": "",
        className: cn(
          buttonLook(variant, big),
          "relative aria-[current=page]:font-semibold aria-[current=page]:text-fg aria-[current=page]:before:absolute aria-[current=page]:before:inset-y-1 aria-[current=page]:before:left-0 aria-[current=page]:before:w-0.5 aria-[current=page]:before:rounded-full aria-[current=page]:before:bg-accent aria-[current=page]:before:content-['']",
          className,
        ),
      } as ComponentProps<"a">,
      props,
    ),
  });
}
