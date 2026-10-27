/**
 * A composer pinned to the bottom of the window as the page scrolls, and the room it takes there:
 * its height, as `--composer-clearance` on the page, which `scroll-padding-bottom` keeps clear, so
 * a control the keyboard reaches, or one scrolled to, is never left under it (the polish pass's
 * finding: the last message's Copy and thumbs under the composer). In a window under 30rem tall it
 * stays in the flow instead (portalr ADR-0080), so it never covers most of the page.
 */

import { type ReactNode, useEffect, useRef } from "react";
import { useCoarsePointer, useTouch } from "./touch";

export function ComposerDock({ children }: { children: ReactNode }) {
  const dock = useRef<HTMLDivElement>(null);
  // On a phone the on-screen keyboard's height is kept on the root, and the dock sits above it.
  const touch = useTouch(useCoarsePointer());
  useEffect(() => touch?.keyboardInset(), [touch]);
  useEffect(() => {
    const element = dock.current;
    const root = document.documentElement;
    if (element === null) {
      return;
    }
    const measure = () =>
      root.style.setProperty("--composer-clearance", `${element.getBoundingClientRect().height}px`);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => {
      observer.disconnect();
      root.style.removeProperty("--composer-clearance");
    };
  }, []);
  return (
    <div
      ref={dock}
      data-composer-dock=""
      className="sticky bottom-(--keyboard-inset,0px) z-10 bg-paper pt-2 short:static"
    >
      {children}
    </div>
  );
}
