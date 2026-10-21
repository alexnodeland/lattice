import { Switch as BaseSwitch } from "@base-ui/react/switch";
import type { ComponentProps } from "react";
import { cn } from "./cn";

type Props = Omit<ComponentProps<typeof BaseSwitch.Root>, "className"> & { className?: string };

/**
 * A switch: Base UI's, whose track takes the working colour when it is on. Under forced colours it
 * takes the system's own, as their controls do: on is the highlight's track and thumb, off a
 * framed track with the text's thumb; disabled, off is a grey frame and thumb, and on a grey track
 * with the page's thumb. So its state never goes with the fills a high-contrast mode drops, and
 * the thumb's side says it too. The system's colours are tokens (tokens.css).
 */
export function Switch({ className, ...props }: Props) {
  return (
    <BaseSwitch.Root
      className={cn(
        "inline-flex h-5 w-9 items-center rounded-full border border-edge bg-paper p-0.5 outline-offset-(--focus-offset) focus-visible:outline-(length:--focus-width) focus-visible:outline-focus data-checked:border-accent data-checked:bg-accent data-disabled:cursor-not-allowed data-disabled:border-line data-disabled:bg-wash forced-color-adjust-none forced-colors:border-system-text forced-colors:bg-system-canvas forced-colors:outline-system-text forced-colors:data-checked:border-system-highlight forced-colors:data-checked:bg-system-highlight forced-colors:data-disabled:border-system-disabled forced-colors:data-checked:data-disabled:bg-system-disabled",
        className,
      )}
      {...props}
    >
      <BaseSwitch.Thumb className="size-4 rounded-full bg-muted transition-transform motion-reduce:transition-none data-checked:translate-x-4 data-checked:bg-on-accent data-disabled:bg-edge forced-color-adjust-none forced-colors:bg-system-text forced-colors:data-checked:bg-system-on-highlight forced-colors:data-disabled:bg-system-disabled forced-colors:data-checked:data-disabled:bg-system-canvas" />
    </BaseSwitch.Root>
  );
}
