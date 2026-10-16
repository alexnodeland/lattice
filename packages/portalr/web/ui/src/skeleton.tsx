import type { ReactNode } from "react";
import { cn } from "./cn";

/**
 * A placeholder for what is being read, in the shape it will take: a bar the height of its line.
 * It pulses, and does not where motion is reduced. It is hidden from assistive technology; what
 * is being read is said in words beside it, as a status.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("block animate-pulse rounded-md bg-line motion-reduce:animate-none", className)}
    />
  );
}

/**
 * What is being read, as a status in words, over placeholders in the shape of what will come, so
 * the page doesn't jump when it does. With no `children` it is only the placeholders.
 */
export function Reading({ children }: { children: ReactNode }) {
  return (
    <div role="status" className="flex flex-col gap-2 text-muted text-sm">
      {children}
      <Skeleton className="h-4 w-2/3" />
      <Skeleton className="h-4 w-1/2" />
    </div>
  );
}
