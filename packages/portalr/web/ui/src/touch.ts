/**
 * A finger as the pointer (portalr ADR-0082): the media questions a part asks, each heard once
 * for every part that asks it, and the touch module, loaded on demand the first time a part with
 * a finger needs it, so a mouse never pays for it. What the module holds is in
 * `on-demand/touch.ts`: a sheet's drag, and the room the on-screen keyboard takes.
 */

import { useEffect, useState, useSyncExternalStore } from "react";

/**
 * A finger is a pointer: `any-pointer`, so a touch laptop with a mouse plugged in counts, as a
 * finger may still reach the screen (the `coarse:` variant is `hover: none`, the look where
 * nothing hovers; this is about what a finger can hit).
 */
const COARSE = "(any-pointer: coarse)";
/** A phone, as the `phone:` variant means it: a narrow window where a finger is a pointer. */
const PHONE = "(max-width: 48rem) and (any-pointer: coarse)";

const queries = new Map<string, { list: MediaQueryList; listeners: Set<() => void> }>();
function query(media: string) {
  let known = queries.get(media);
  if (known === undefined) {
    const list = matchMedia(media);
    const listeners = new Set<() => void>();
    list.addEventListener("change", () => {
      for (const listener of listeners) {
        listener();
      }
    });
    known = { list, listeners };
    queries.set(media, known);
  }
  return known;
}

/** Whether `media` matches now, re-read as it changes. */
function useMedia(media: string): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const { listeners } = query(media);
      listeners.add(onChange);
      return () => listeners.delete(onChange);
    },
    () => query(media).list.matches,
  );
}

/** Whether a finger is a pointer here, as on a phone or a touch laptop. */
export const useCoarsePointer = (): boolean => useMedia(COARSE);

/** Whether this is a phone: narrow, with a finger as a pointer. */
export const usePhone = (): boolean => useMedia(PHONE);

/**
 * Whether this is a phone at this moment, read afresh where a choice is made, as a tap's: a query
 * list kept from before a resize or a turn may not have caught up yet.
 */
export const phoneNow = (): boolean => matchMedia(PHONE).matches;

export type Touch = typeof import("./on-demand/touch");

let loading: Promise<Touch> | null = null;
/** The touch module, asked for once; asked again after a failed load, as a reload may succeed. */
const loadTouch = () => {
  loading ??= import("./on-demand/touch").catch((error: unknown) => {
    loading = null;
    throw error;
  });
  return loading;
};

/** The touch module once `wanted`, such as when a sheet opens on a phone; null until then. */
export function useTouch(wanted: boolean): Touch | null {
  const [touch, setTouch] = useState<Touch | null>(null);
  useEffect(() => {
    if (!wanted || touch !== null) {
      return;
    }
    let on = true;
    loadTouch().then(
      (loaded) => on && setTouch(loaded),
      () => undefined,
    );
    return () => {
      on = false;
    };
  }, [wanted, touch]);
  return wanted ? touch : null;
}
