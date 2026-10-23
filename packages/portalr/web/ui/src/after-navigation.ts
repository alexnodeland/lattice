/**
 * Where the focus goes after a page changes inside the app (portalr ADR-0068): to the new page's
 * heading, its `h1`, so a reader who followed a link starts at its top rather than nowhere. Only
 * where the focus was lost, to the document's body, as it is when the link followed is gone with
 * its page: a rail's or a drawer's link that stays keeps it, and so does a page that put it
 * somewhere itself, such as a not-found's heading or a pending question.
 */

import { useEffect } from "react";

/**
 * Move the focus to the page's heading, if the focus is nowhere; whether there was a heading to
 * move it to, or no need.
 */
export function focusPageHeading(): boolean {
  const at = document.activeElement;
  if (at !== null && at !== document.body && at.isConnected) {
    return true;
  }
  const heading = document.querySelector<HTMLElement>("#main h1");
  if (heading === null) {
    return false;
  }
  if (!heading.hasAttribute("tabindex")) {
    heading.tabIndex = -1;
  }
  heading.focus({ preventScroll: true });
  return true;
}

/** How long a page that draws its heading late, such as a thread before its stream is live, has. */
const LATE = 2_000;

/** What a router tells of a navigation it finished: whether its path changed. */
type Resolved = { readonly pathChanged: boolean };

/**
 * Focus the page's heading after each navigation that changed the path, once the new page has
 * drawn; never on the first load, which starts at the document as a browser's does.
 * `subscribe` is the router's, such as `(on) => router.subscribe("onResolved", on)`, and must be
 * stable.
 */
export function useHeadingAfterNavigation(
  subscribe: (listener: (event: Resolved) => void) => () => void,
) {
  useEffect(() => {
    let frame = 0;
    let watching: MutationObserver | null = null;
    let giveUp = 0;
    const stop = () => {
      cancelAnimationFrame(frame);
      watching?.disconnect();
      watching = null;
      clearTimeout(giveUp);
    };
    const unsubscribe = subscribe((event) => {
      if (!event.pathChanged) {
        return;
      }
      stop();
      // A frame for the new page to draw, and one for its effects to have run; a page whose
      // heading comes later is watched for it, a while.
      frame = requestAnimationFrame(() => {
        frame = requestAnimationFrame(() => {
          if (focusPageHeading()) {
            return;
          }
          watching = new MutationObserver(() => focusPageHeading() && stop());
          watching.observe(document.body, { childList: true, subtree: true });
          giveUp = window.setTimeout(stop, LATE);
        });
      });
    });
    return () => {
      unsubscribe();
      stop();
    };
  }, [subscribe]);
}
