/**
 * Whether an element is near the window (portalr ADR-0055): a thread of many files reads and
 * polls only what is in sight or about to be. Once near, it stays read; while it is far, its
 * reads again pause.
 */

import { type RefObject, useEffect, useState } from "react";

/** How far outside the window an element counts as near. */
const MARGIN = "600px";

export function useNear(element: RefObject<Element | null>) {
  const [near, setNear] = useState(typeof IntersectionObserver === "undefined");
  const [seen, setSeen] = useState(near);
  useEffect(() => {
    const target = element.current;
    if (target === null || typeof IntersectionObserver === "undefined") {
      return;
    }
    const observer = new IntersectionObserver(
      (entries) => {
        const now = entries.some((entry) => entry.isIntersecting);
        setNear(now);
        if (now) {
          setSeen(true);
        }
      },
      { rootMargin: MARGIN },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [element]);
  return { near, seen } as const;
}
