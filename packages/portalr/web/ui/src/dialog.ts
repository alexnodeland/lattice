/**
 * The look the kit's dialogs share: Base UI's Dialog, and its AlertDialog, on the surface over the
 * scrim. A dialog's title, what it's about, what it holds, and its actions, last, at its end.
 */

export const backdrop =
  "fixed inset-0 z-40 bg-scrim transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

export const popup =
  "fixed top-1/2 left-1/2 z-50 flex max-h-[85dvh] w-[min(32rem,calc(100vw-2rem))] -translate-x-1/2 -translate-y-1/2 flex-col gap-4 overflow-y-auto rounded-lg border border-line bg-surface p-5 text-fg shadow-lg outline-none transition-[opacity,scale] duration-150 data-ending-style:scale-98 data-starting-style:scale-98 data-ending-style:opacity-0 data-starting-style:opacity-0 motion-reduce:transition-none";

export const title = "font-semibold text-fg text-lg";

export const description = "text-muted text-sm";

export const actions = "flex flex-wrap justify-end gap-2";
