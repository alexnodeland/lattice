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

/** Whether an element can take the focus by Tab: in the order, enabled, drawn and not inert. */
function reachable(element: HTMLElement): boolean {
  // A <details>' first summary is in the order, though the DOM gives it no tab index.
  const ordered = element.tabIndex >= 0 || element.matches("details > summary:first-of-type");
  return (
    ordered &&
    !element.matches(":disabled") &&
    !element.closest("[inert]") &&
    // Not drawn: hidden, or inside a closed <details>.
    element.checkVisibility({ visibilityProperty: true })
  );
}

/** The radios of a radio's group, by its name, in its form or else in the box, that Tab reaches. */
function groupOf(radio: HTMLInputElement, within: Element): HTMLInputElement[] {
  return [
    ...(radio.form ?? within).querySelectorAll<HTMLInputElement>(
      `input[type=radio][name="${CSS.escape(radio.name)}"]`,
    ),
  ].filter(reachable);
}

const isRadio = (element: Element | null): element is HTMLInputElement =>
  element instanceof HTMLInputElement && element.type === "radio" && element.name !== "";

/**
 * Whether an element is a stop of Tab in a box. Of a group of radios, the checked one is; where
 * none is, Tab enters at the first and Shift+Tab at the last, so both are.
 */
function isStop(element: HTMLElement, within: Element): boolean {
  if (!reachable(element)) {
    return false;
  }
  if (isRadio(element)) {
    const group = groupOf(element, within);
    const checked = group.find((radio) => radio.checked);
    return checked ? element === checked : element === group[0] || element === group.at(-1);
  }
  return true;
}

/** Whether `at` is `stop`, or a radio of its group, where Tab leaves the group as one stop. */
function atStop(at: Element, stop: HTMLElement, within: Element): boolean {
  return at === stop || (isRadio(at) && isRadio(stop) && groupOf(stop, within).includes(at));
}

/**
 * Keep Tab within a box, as a modal dialog does: from its last stop, or past it, to its first,
 * and Shift+Tab from its first, or before it, to its last. The page behind is inert, but without
 * this Tab leaves for the browser's own controls, through the document, before it comes back
 * (WCAG 2.4.3). A key something else took, focus in a popup of its own outside the box, and a box
 * with no stop are left alone. Keys pressed inside an app's frame never reach this page, so Tab
 * from a frame that is the last stop leaves as the browser has it.
 */
function wrap(within: Element, event: KeyboardEvent) {
  const at = document.activeElement;
  const lost = at === null || at === document.body;
  if (event.defaultPrevented || !(lost || within.contains(at))) {
    return;
  }
  const stops = [...within.querySelectorAll<HTMLElement>("*")].filter((each) =>
    isStop(each, within),
  );
  const [first, last] = [stops[0], stops.at(-1)];
  if (first === undefined || last === undefined) {
    return;
  }
  const leaving =
    lost ||
    (event.shiftKey
      ? atStop(at, first, within) ||
        Boolean(first.compareDocumentPosition(at) & Node.DOCUMENT_POSITION_PRECEDING)
      : atStop(at, last, within) ||
        Boolean(last.compareDocumentPosition(at) & Node.DOCUMENT_POSITION_FOLLOWING));
  if (leaving) {
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
