/**
 * The look the kit's menus share: Base UI's Menu, on the surface. The item the keyboard or the
 * pointer is on is washed, in the working colour, and ringed in the focus colour, which stands 3:1
 * or more from the surface where the wash alone would not.
 */

export const popup =
  "min-w-56 rounded-lg border border-line bg-surface p-1.5 text-fg text-sm shadow-lg outline-none transition-[opacity,scale] duration-150 data-ending-style:scale-98 data-starting-style:scale-98 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

export const groupLabel = "px-2.5 pt-1.5 pb-1 font-semibold text-muted text-xs";

export const item =
  "flex cursor-default items-center justify-between gap-3 rounded-md px-2.5 py-1.5 outline-none data-highlighted:bg-wash data-highlighted:text-accent data-highlighted:ring-2 data-highlighted:ring-focus data-highlighted:ring-inset";

export const separator = "my-1.5 h-px bg-line";
