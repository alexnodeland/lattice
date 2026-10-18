/**
 * What a part loads only when a page needs it, such as `Markdown`'s math and a dashboard's charts:
 * each add-on is a module of `on-demand/`, which the bundle splits into chunks of its own, loaded
 * the first time a page asks for one and kept for the page's life (portalr ADR-0044). Until it
 * has loaded, a caller has nothing; and one that won't load says so, so that a caller shows what
 * it would draw another way, as it does where the add-on is off.
 */

import { useCallback, useEffect, useSyncExternalStore } from "react";

/** An add-on as a caller has it: its module once loaded, or null, and whether it failed to load. */
export interface Loaded<T> {
  readonly module: T | null;
  readonly failed: boolean;
}

type Loading<T> = {
  /** Replaced, never changed, as it loads, so a render can tell it changed by its identity. */
  state: Loaded<T>;
  started: boolean;
  readonly listeners: Set<() => void>;
};

const NOTHING: Loaded<never> = { module: null, failed: false };

const loads = new Map<() => Promise<unknown>, Loading<unknown>>();

function loading<T>(load: () => Promise<T>): Loading<T> {
  let found = loads.get(load) as Loading<T> | undefined;
  if (!found) {
    found = { state: NOTHING, started: false, listeners: new Set() };
    loads.set(load, found);
  }
  return found;
}

function start<T>(load: () => Promise<T>): void {
  const entry = loading(load);
  if (entry.started) {
    return;
  }
  entry.started = true;
  const settle = (state: Loaded<T>) => {
    entry.state = state;
    for (const listener of entry.listeners) {
      listener();
    }
  };
  load().then(
    (module) => settle({ module, failed: false }),
    () => settle({ module: null, failed: true }),
  );
}

/**
 * The add-on `load` gives, as it loads: its module once it has, and whether it failed to; `load`
 * starts only when `wanted`, and while it isn't, the caller has nothing.
 */
export function useLoaded<T>(load: (() => Promise<T>) | undefined, wanted = true): Loaded<T> {
  const entry = load && loading(load);
  const subscribe = useCallback(
    (changed: () => void) => {
      entry?.listeners.add(changed);
      return () => {
        entry?.listeners.delete(changed);
      };
    },
    [entry],
  );
  const state = useSyncExternalStore(subscribe, () => entry?.state ?? NOTHING);
  useEffect(() => {
    if (load && wanted) {
      start(load);
    }
  }, [load, wanted]);
  return wanted ? state : NOTHING;
}

/** The loaded module `load` gives, once it has, or null; `load` starts only when `wanted`. */
export const useOnDemand = <T>(load: (() => Promise<T>) | undefined, wanted = true): T | null =>
  useLoaded(load, wanted).module;
