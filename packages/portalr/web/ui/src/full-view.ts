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

/** Whether an element is a stop of Tab: focusable in order, enabled, drawn, and not inert. */
function isStop(element: HTMLElement): boolean {
  // A <details>' summary is a stop, though the DOM gives it no tab index.
  const ordered = element.tabIndex >= 0 || element.matches("details > summary");
  if (!ordered || element.matches(":disabled") || element.closest("[inert]")) {
    return false;
  }
  if (!element.checkVisibility({ visibilityProperty: true })) {
    return false; // not drawn: hidden, or in a closed <details>
  }
  // Of a group of radios, Tab stops at the checked one, or at the first where none is.
  if (element instanceof HTMLInputElement && element.type === "radio" && element.name !== "") {
    const group = [
      ...(element.form ?? document).querySelectorAll<HTMLInputElement>(
        `input[type=radio][name="${CSS.escape(element.name)}"]`,
      ),
    ];
    return element === (group.find((radio) => radio.checked) ?? group[0]);
  }
  return true;
}

/**
 * Keep Tab within a box, as a modal dialog does: from its last stop to its first, and Shift+Tab
 * from its first to its last. The page behind is inert, but without this Tab leaves for the
 * browser's own controls, through the document, before it comes back (WCAG 2.4.3). A box with no
 * stop leaves Tab to the browser.
 */
function wrap(within: Element, event: KeyboardEvent) {
  const stops = [...within.querySelectorAll<HTMLElement>("*")].filter(isStop);
  const [first, last] = [stops[0], stops.at(-1)];
  if (first === undefined || last === undefined) {
    return;
  }
  const at = document.activeElement;
  if (event.shiftKey ? at === first || !within.contains(at) : at === last) {
    event.preventDefault();
    (event.shiftKey ? last : first).focus();
  }
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
      if (event.key === "Tab") {
        wrap(within, event);
        return;
      }
      // Something inside that took Escape keeps it, but the back button's own tooltip, which
      // takes it to close itself, doesn't: one Escape leaves (portalr ADR-0061).
      if (event.key === "Escape" && (!event.defaultPrevented || event.target === back.current)) {
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
