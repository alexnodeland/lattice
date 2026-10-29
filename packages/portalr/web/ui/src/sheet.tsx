/**
 * A bottom sheet (portalr ADR-0082): on a phone, where a finger is the pointer and the window is
 * narrow, a dialog, a menu or a popover sits along the bottom of the window instead of floating,
 * the full width (to 36rem, centred past it), rounded at its top, with a handle, sliding up as it
 * opens and down as it closes (not where motion is reduced), scrolling inside itself past the
 * window's height, and keeping the home indicator clear. It stays what it was: a dialog with its
 * focus kept in, a menu with its items, so nothing else changes. Its drag, by the handle, is the
 * touch module's, loaded the first time a sheet opens on a phone; the handle is shown once the
 * drag listens.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { usePhone, useTouch } from "./touch";

/**
 * The sheet's classes (styles.css): a dialog's popup places itself; a menu's or a popover's
 * positioner takes the place and its popup the look. The `!` beats the place Base UI writes
 * inline and the popup's own look.
 */
export const sheet = "phone:!as-sheet";
export const sheetPositioner = "phone:!as-sheet-positioner";
export const sheetPopup = "phone:!as-sheet-popup";

/**
 * The handle at a sheet's top, which the finger drags: a small pill to see (36 by 4px) in a band a
 * finger can hit, 20px tall and the sheet's width, shown once the drag listens. Under forced
 * colours its edge is drawn, as its fill is not.
 */
export function SheetHandle() {
  return (
    <span
      data-sheet-handle=""
      aria-hidden="true"
      className="hidden shrink-0 cursor-grab touch-none py-2 in-data-sheet-drag:phone:block"
    >
      <span className="mx-auto block h-1 w-9 rounded-full border border-transparent bg-edge" />
    </span>
  );
}

/**
 * A sheet's drag for the popup the returned ref is given, while it is open on a phone. The popup
 * is held as state, as Base UI mounts it a render after `open` turns, so a ref alone would be
 * read too soon. The touch module is loaded the first time a sheet opens.
 */
export function useSheet(open: boolean, close: () => void) {
  const phone = usePhone();
  const touch = useTouch(phone && open);
  const [popup, setPopup] = useState<HTMLElement | null>(null);
  // The latest `close`, so a new one each render doesn't re-bind the drag.
  const closing = useRef(close);
  closing.current = close;
  useEffect(() => {
    if (!open || !phone || touch === null || popup === null) {
      return;
    }
    return touch.sheetDrag(popup, () => closing.current());
  }, [open, phone, touch, popup]);
  return useCallback((node: HTMLElement | null) => setPopup(node), []);
}
