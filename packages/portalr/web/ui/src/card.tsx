import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement } from "react";
import { cn } from "./cn";

type Props = Omit<ComponentProps<"div">, "className"> & {
  /** What to render as the card, such as a `<section>` named by its heading: a `<div>` without. */
  render?: ReactElement;
  className?: string;
};

/** A card: what asks something of the reader, such as an approval, on the surface, outlined. */
export function Card({ render, className, ...props }: Props) {
  return useRender({
    defaultTagName: "div",
    render,
    props: mergeProps<"div">(
      {
        className: cn(
          "rounded-lg border border-line bg-surface p-4 text-fg shadow-raised",
          className,
        ),
      },
      props,
    ),
  });
}
