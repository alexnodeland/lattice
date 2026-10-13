import { mergeProps } from "@base-ui/react/merge-props";
import { useRender } from "@base-ui/react/use-render";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { cn } from "./cn";

/** A list of rows, lined one under another, named for what they are. */
export function Rows({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ul aria-label={label} className="flex flex-col divide-y divide-line border-line border-y">
      {children}
    </ul>
  );
}

/** One row: what it is, then what is said about it. Its `RowLink`, if any, is the whole row's target. */
export function Row({
  children,
  ...props
}: Omit<ComponentProps<"li">, "className"> & { children: ReactNode }) {
  return (
    <li
      className="relative flex flex-wrap items-center gap-x-3 gap-y-1 px-2 py-3 text-sm has-[a:hover]:bg-wash has-[a:focus-visible]:bg-wash"
      {...props}
    >
      {children}
    </li>
  );
}

type RowLinkProps = Omit<ComponentProps<"a">, "className"> & {
  /** What to render as the link, such as the router's own. */
  render?: ReactElement;
  className?: string;
};

/** A row's link, stretched over the row, so the whole row takes the pointer. */
export function RowLink({ render, className, ...props }: RowLinkProps) {
  return useRender({
    defaultTagName: "a",
    render,
    props: mergeProps<"a">(
      {
        className: cn(
          "font-semibold text-accent underline underline-offset-2 outline-none after:absolute after:inset-0 after:content-['']",
          className,
        ),
      },
      props,
    ),
  });
}
