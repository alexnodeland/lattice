import { Switch as BaseSwitch } from "@base-ui/react/switch";
import type { ComponentProps } from "react";
import { cn } from "./cn";

type Props = Omit<ComponentProps<typeof BaseSwitch.Root>, "className"> & { className?: string };

/** A switch: Base UI's, whose track takes the working colour when it is on. */
export function Switch({ className, ...props }: Props) {
  return (
    <BaseSwitch.Root
      className={cn(
        "inline-flex h-5 w-9 items-center rounded-full border border-line bg-paper p-0.5 outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus data-[checked]:border-accent data-[checked]:bg-accent data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      <BaseSwitch.Thumb className="size-4 rounded-full bg-muted transition-transform motion-reduce:transition-none data-[checked]:translate-x-4 data-[checked]:bg-on-accent" />
    </BaseSwitch.Root>
  );
}
