import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement } from "react";
import { cn } from "./cn";

type Props = Omit<ComponentProps<"a">, "className"> & {
  /** What to render as the link, such as the router's own: an `<a>` without one. */
  render?: ReactElement;
  className?: string;
};

/** A link in running text, in the working colour; a router's link renders through `render`. */
export function TextLink({ render, className, ...props }: Props) {
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(
          "text-accent underline underline-offset-2 outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus",
          className,
        ),
      },
      props,
    ),
  });
}
