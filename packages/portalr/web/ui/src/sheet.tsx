/**
 * A bottom sheet (portalr ADR-0082): on a phone, where a finger is the pointer and the window is
 * narrow, a dialog, a menu or a popover sits along the bottom of the window instead of floating,
 * the full width, rounded at its top, with a handle, sliding up as it opens and down as it closes
 * (not where motion is reduced), scrolling inside itself past the window's height, and keeping
 * the home indicator clear. It stays what it was: a dialog with its focus kept in, a menu with
 * its items, so nothing else changes. Its drag, by the handle or from its top, is the touch
 * module's, loaded the first time it is needed.
 */

import { type RefObject, useEffect, useSyncExternalStore } from "react";
import { useTouch } from "./touch";

const PHONE = "(max-width: 48rem) and (any-pointer: coarse)";
const phone = {
  query: null as MediaQueryList | null,
  listeners: new Set<() => void>(),
  subscribe(onChange: () => void) {
    if (phone.query === null) {
      phone.query = matchMedia(PHONE);
      phone.query.addEventListener("change", () => {
        for (const listener of phone.listeners) {
          listener();
        }
      });
    }
    phone.listeners.add(onChange);
    return () => phone.listeners.delete(onChange);
  },
  matches: () => (phone.query ?? matchMedia(PHONE)).matches,
};

/** Whether this is a phone, as the `phone:` variant means it: narrow, with a finger as a pointer. */
export function usePhone(): boolean {
  return useSyncExternalStore(phone.subscribe, phone.matches);
}

/**
 * The sheet's classes (styles.css): a dialog's popup places itself; a menu's or a popover's
 * positioner takes the place and its popup the look. The `!` beats the place Base UI writes
 * inline and the popup's own look.
 */
export const sheet = "phone:!as-sheet";
export const sheetPositioner = "phone:!as-sheet-positioner";
export const sheetPopup = "phone:!as-sheet-popup";

/** The handle at a sheet's top: seen on a phone alone, where it is what the finger drags. */
export function SheetHandle() {
  return (
    <span
      data-sheet-handle=""
      aria-hidden="true"
      className="mx-auto mb-2 hidden h-1 w-10 shrink-0 cursor-grab touch-none rounded-full bg-edge phone:block"
    />
  );
}

/** Gives the popup at `ref` a sheet's drag while it is open, where a finger is the pointer. */
export function useSheet(ref: RefObject<HTMLElement | null>, open: boolean, close: () => void) {
  const touch = useTouch();
  useEffect(() => {
    const popup = ref.current;
    if (!open || touch === null || popup === null) {
      return;
    }
    return touch.sheetDrag(popup, close);
  }, [ref, open, touch, close]);
}
