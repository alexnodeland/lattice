/**
 * A box that fills the window, as a modal dialog, and goes back to its place in the page, without
 * being moved or drawn again, so what is in it keeps its state: an app's frame, a form's answers,
 * a file's page (portalr ADR-0052, ADR-0055).
 */

import { useEffect, useRef, useState } from "react";

/**
 * Make everything but `within` and its ancestors inert, as a modal's page is behind it, and give
 * back a way to undo it: only what this made inert is let go.
 */
export function inertOutside(within: Element): () => void {
  const made: Element[] = [];
  for (let node: Element | null = within; node?.parentElement; node = node.parentElement) {
    for (const sibling of node.parentElement.children) {
      if (sibling !== node && !sibling.hasAttribute("inert")) {
        sibling.setAttribute("inert", "");
        made.push(sibling);
      }
    }
  }
  return () => {
    for (const each of made) {
      each.removeAttribute("inert");
    }
  };
}

/**
 * A full view: whether it is open, and the refs of the box that fills the window and of the way
 * back, which is focused as it opens. While it is open the page behind it is inert, and Escape
 * not already taken returns it; on its return, focus goes back to the way back, in its place.
 */
export function useFullView() {
  const [full, setFull] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const back = useRef<HTMLButtonElement>(null);
  const opened = useRef(false);
  useEffect(() => {
    const within = box.current;
    if (!full || within === null) {
      if (opened.current) {
        opened.current = false;
        back.current?.focus();
      }
      return;
    }
    opened.current = true;
    const restore = inertOutside(within);
    back.current?.focus();
    const leave = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !event.defaultPrevented) {
        setFull(false);
      }
    };
    addEventListener("keydown", leave);
    return () => {
      removeEventListener("keydown", leave);
      restore();
    };
  }, [full]);
  return { full, setFull, box, back } as const;
}
