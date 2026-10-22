/**
 * A composer pinned to the bottom of the window as the page scrolls, and the room it takes there:
 * its height, as `--composer-clearance` on the page, which `scroll-padding-bottom` keeps clear, so
 * a control the keyboard reaches, or one scrolled to, is never left under it (the polish pass's
 * finding: the last message's Copy and thumbs under the composer).
 */

import { type ReactNode, useEffect, useRef } from "react";

export function ComposerDock({ children }: { children: ReactNode }) {
  const dock = useRef<HTMLDivElement>(null);
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
    <div ref={dock} data-composer-dock="" className="sticky bottom-0 z-10 bg-paper pt-2 pb-4">
      {children}
    </div>
  );
}
