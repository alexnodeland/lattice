import { Switch as BaseSwitch } from "@base-ui/react/switch";
import type { ComponentProps } from "react";
import { cn } from "./cn";

type Props = Omit<ComponentProps<typeof BaseSwitch.Root>, "className"> & { className?: string };

/**
 * A switch: Base UI's, whose track takes the working colour when it is on. Under forced colours it
 * takes the system's own, as their controls do: on is the highlight's track and thumb, off a
 * framed track with the text's thumb, disabled the grey's, so its state never goes with the fills
 * a high-contrast mode drops; the thumb's side says it too.
 */
export function Switch({ className, ...props }: Props) {
  return (
    <BaseSwitch.Root
      className={cn(
        "inline-flex h-5 w-9 items-center rounded-full border border-edge bg-paper p-0.5 outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus data-checked:border-accent data-checked:bg-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-wash forced-color-adjust-none forced-colors:border-[CanvasText] forced-colors:bg-[Canvas] forced-colors:outline-[CanvasText] forced-colors:data-checked:border-[Highlight] forced-colors:data-checked:bg-[Highlight] forced-colors:data-disabled:border-[GrayText]",
        className,
      )}
      {...props}
    >
      <BaseSwitch.Thumb className="size-4 rounded-full bg-muted transition-transform motion-reduce:transition-none data-checked:translate-x-4 data-checked:bg-on-accent data-disabled:bg-edge forced-color-adjust-none forced-colors:bg-[CanvasText] forced-colors:data-checked:bg-[HighlightText] forced-colors:data-disabled:bg-[GrayText]" />
    </BaseSwitch.Root>
  );
}
