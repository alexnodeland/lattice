/**
 * A finger as the pointer (portalr ADR-0082): one media question, heard once for every part that
 * asks, and the touch module, loaded on demand the first time a page with a finger needs it, so
 * a mouse never pays for it. What the module holds is in `on-demand/touch.ts`: a sheet's drag,
 * and the room the on-screen keyboard takes.
 */

import { useEffect, useState, useSyncExternalStore } from "react";

const COARSE = "(any-pointer: coarse)";

const pointer = {
  query: null as MediaQueryList | null,
  listeners: new Set<() => void>(),
  subscribe(onChange: () => void) {
    if (pointer.query === null) {
      pointer.query = matchMedia(COARSE);
      pointer.query.addEventListener("change", () => {
        for (const listener of pointer.listeners) {
          listener();
        }
      });
    }
    pointer.listeners.add(onChange);
    return () => pointer.listeners.delete(onChange);
  },
  coarse: () => (pointer.query ?? matchMedia(COARSE)).matches,
};

/** Whether a finger is a pointer here, as on a phone or a touch laptop. */
export function useCoarsePointer(): boolean {
  return useSyncExternalStore(pointer.subscribe, pointer.coarse);
}

export type Touch = typeof import("./on-demand/touch");

let loading: Promise<Touch> | null = null;
const loadTouch = () => {
  loading ??= import("./on-demand/touch");
  return loading;
};

/** The touch module, once a finger is the pointer; null until then, and where there is none. */
export function useTouch(): Touch | null {
  const coarse = useCoarsePointer();
  const [touch, setTouch] = useState<Touch | null>(null);
  useEffect(() => {
    if (!coarse || touch !== null) {
      return;
    }
    let on = true;
    void loadTouch().then((loaded) => on && setTouch(loaded));
    return () => {
      on = false;
    };
  }, [coarse, touch]);
  return coarse ? touch : null;
}
