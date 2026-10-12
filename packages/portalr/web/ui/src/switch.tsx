import { Switch as BaseSwitch } from "@base-ui/react/switch";
import type { ComponentProps } from "react";

/** A switch: Base UI's, whose track takes the working colour when it is on. */
export function Switch(props: ComponentProps<typeof BaseSwitch.Root>) {
  return (
    <BaseSwitch.Root
      className="inline-flex h-5 w-9 items-center rounded-full border border-line bg-paper p-0.5 outline-offset-2 focus-visible:outline-2 focus-visible:outline-focus data-[checked]:border-accent data-[checked]:bg-accent"
      {...props}
    >
      <BaseSwitch.Thumb className="size-4 rounded-full bg-graphite transition-transform data-[checked]:translate-x-4 data-[checked]:bg-on-accent" />
    </BaseSwitch.Root>
  );
}
