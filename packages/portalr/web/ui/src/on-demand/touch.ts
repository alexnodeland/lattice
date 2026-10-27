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
 * Lets a sheet be dragged down by its handle, and closes it when let go far enough down or
 * flicked; otherwise, or when the browser takes the gesture, it springs back. The sheet follows
 * the finger through `--sheet-drag`, which its place reads (styles.css), so the place's own
 * transform is never fought. It marks the sheet `data-sheet-drag` while it listens, which shows
 * the handle. Returns what undoes it.
 */
export function sheetDrag(sheet: HTMLElement, close: () => void): () => void {
  let from: { y: number; at: number; id: number; handle: HTMLElement } | null = null;
  sheet.style.setProperty("--sheet-drag", "0px");
  const settle = (dy: number) => {
    sheet.style.transition = "";
    sheet.style.setProperty("--sheet-drag", `${dy}px`);
  };
  const start = (event: PointerEvent) => {
    if (event.pointerType === "mouse" || from !== null) {
      return;
    }
    const handle = (event.target as Element).closest<HTMLElement>("[data-sheet-handle]");
    if (handle === null) {
      return;
    }
    from = { y: event.clientY, at: event.timeStamp, id: event.pointerId, handle };
    handle.setPointerCapture?.(event.pointerId);
    sheet.style.transition = "none";
  };
  const move = (event: PointerEvent) => {
    if (from === null || event.pointerId !== from.id) {
      return;
    }
    sheet.style.setProperty("--sheet-drag", `${Math.max(0, event.clientY - from.y)}px`);
  };
  const end = (event: PointerEvent) => {
    if (from === null || event.pointerId !== from.id) {
      return;
    }
    const dy = Math.max(0, event.clientY - from.y);
    const speed = dy / Math.max(1, event.timeStamp - from.at);
    from = null;
    if (dy > sheet.offsetHeight * CLOSE_AT || (dy > FLICK_AT && speed > FLICK)) {
      // Closed from where it was let go: its closing slide carries on from there.
      settle(dy);
      close();
    } else {
      settle(0);
    }
  };
  // The browser took the gesture, to scroll say: never a close.
  const cancel = (event: PointerEvent) => {
    if (from !== null && event.pointerId === from.id) {
      from = null;
      settle(0);
    }
  };
  sheet.addEventListener("pointerdown", start);
  sheet.addEventListener("pointermove", move);
  sheet.addEventListener("pointerup", end);
  sheet.addEventListener("pointercancel", cancel);
  sheet.dataset.sheetDrag = "";
  return () => {
    sheet.removeEventListener("pointerdown", start);
    sheet.removeEventListener("pointermove", move);
    sheet.removeEventListener("pointerup", end);
    sheet.removeEventListener("pointercancel", cancel);
    delete sheet.dataset.sheetDrag;
    sheet.style.transition = "";
    // The offset stays: a sheet closing from where it was let go slides on from there.
  };
}

/**
 * Keeps `--keyboard-inset` on the root at the height the on-screen keyboard covers, as the
 * visual viewport says, so a composer pinned to the bottom sits above it where the page itself
 * doesn't shrink (`interactive-widget=resizes-content` is honoured by some browsers, not all). A
 * pinch zoom shrinks the visual viewport too, and is no keyboard: nothing is kept then. While
 * the keyboard is up the root is marked `data-keyboard`, as the home indicator is under it then.
 * Returns what stops it.
 */
export function keyboardInset(root: HTMLElement = document.documentElement): () => void {
  const viewport = window.visualViewport;
  if (!viewport) {
    return () => undefined;
  }
  let frame = 0;
  const measure = () => {
    frame = 0;
    const zoomed = viewport.scale > 1.01;
    const covered = zoomed
      ? 0
      : Math.max(0, window.innerHeight - viewport.height - viewport.offsetTop);
    root.style.setProperty("--keyboard-inset", `${Math.round(covered)}px`);
    root.toggleAttribute("data-keyboard", covered > 0);
  };
  // Resize and scroll come together, and often: one measure a frame.
  const soon = () => {
    frame ||= requestAnimationFrame(measure);
  };
  measure();
  viewport.addEventListener("resize", soon);
  viewport.addEventListener("scroll", soon);
  return () => {
    viewport.removeEventListener("resize", soon);
    viewport.removeEventListener("scroll", soon);
    cancelAnimationFrame(frame);
    root.style.removeProperty("--keyboard-inset");
    root.removeAttribute("data-keyboard");
  };
}
