/**
 * What a finger needs and a mouse never loads (portalr ADR-0082): a sheet's drag, down and away,
 * and the room the on-screen keyboard takes, kept clear by what is pinned to the bottom.
 */

/** How far down a sheet is dragged before letting go closes it, as a share of its height. */
const CLOSE_AT = 1 / 3;
/** A flick: faster than this, in pixels a millisecond, and past `FLICK_AT` pixels, closes it. */
const FLICK = 0.6;
const FLICK_AT = 24;

/**
 * Lets a sheet be dragged down by its handle, or from anywhere in it that isn't scrolled, and
 * closes it when let go far enough down or flicked; otherwise it springs back. Returns what
 * undoes it.
 */
export function sheetDrag(sheet: HTMLElement, close: () => void): () => void {
  let from: { y: number; at: number; id: number } | null = null;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const start = (event: PointerEvent) => {
    if (event.pointerType === "mouse") {
      return;
    }
    const handle = (event.target as Element).closest("[data-sheet-handle]");
    // From the body, only when its scroll is at the top: otherwise the finger scrolls it.
    if (handle === null && sheet.scrollTop > 0) {
      return;
    }
    from = { y: event.clientY, at: event.timeStamp, id: event.pointerId };
    sheet.style.transition = "none";
  };
  const move = (event: PointerEvent) => {
    if (from === null || event.pointerId !== from.id) {
      return;
    }
    const dy = Math.max(0, event.clientY - from.y);
    sheet.style.transform = `translateY(${dy}px)`;
  };
  const end = (event: PointerEvent) => {
    if (from === null || event.pointerId !== from.id) {
      return;
    }
    const dy = Math.max(0, event.clientY - from.y);
    const speed = dy / Math.max(1, event.timeStamp - from.at);
    from = null;
    sheet.style.transition = "";
    sheet.style.transform = "";
    if (dy > sheet.offsetHeight * CLOSE_AT || (dy > FLICK_AT && speed > FLICK)) {
      close();
    } else if (reduced) {
      sheet.style.transform = "";
    }
  };
  sheet.addEventListener("pointerdown", start);
  sheet.addEventListener("pointermove", move);
  sheet.addEventListener("pointerup", end);
  sheet.addEventListener("pointercancel", end);
  return () => {
    sheet.removeEventListener("pointerdown", start);
    sheet.removeEventListener("pointermove", move);
    sheet.removeEventListener("pointerup", end);
    sheet.removeEventListener("pointercancel", end);
    sheet.style.transition = "";
    sheet.style.transform = "";
  };
}

/**
 * Keeps `--keyboard-inset` on the root at the height the on-screen keyboard covers, as the
 * visual viewport says, so a composer pinned to the bottom sits above it where the page itself
 * doesn't shrink (`interactive-widget=resizes-content` is honoured by some browsers, not all).
 * Returns what stops it.
 */
export function keyboardInset(root: HTMLElement = document.documentElement): () => void {
  const viewport = window.visualViewport;
  if (!viewport) {
    return () => undefined;
  }
  const measure = () => {
    const covered = Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
    root.style.setProperty("--keyboard-inset", `${Math.round(covered)}px`);
  };
  measure();
  viewport.addEventListener("resize", measure);
  viewport.addEventListener("scroll", measure);
  return () => {
    viewport.removeEventListener("resize", measure);
    viewport.removeEventListener("scroll", measure);
    root.style.removeProperty("--keyboard-inset");
  };
}
