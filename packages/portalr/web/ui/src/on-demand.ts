/**
 * What `Markdown` loads only when a message needs it: each add-on is a module of `on-demand/`,
 * which the bundle splits into chunks of its own, loaded the first time a page asks for one and
 * kept for the page's life (portalr ADR-0044). Until it has loaded, or if it fails to, a caller
 * has nothing, and shows what it would draw as its source.
 */

import { useCallback, useEffect, useSyncExternalStore } from "react";

type Loading<T> = {
  value: T | null;
  started: boolean;
  readonly listeners: Set<() => void>;
};

const loads = new Map<() => Promise<unknown>, Loading<unknown>>();

function loading<T>(load: () => Promise<T>): Loading<T> {
  let found = loads.get(load) as Loading<T> | undefined;
  if (!found) {
    found = { value: null, started: false, listeners: new Set() };
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
  load().then(
    (value) => {
      entry.value = value;
      for (const listener of entry.listeners) {
        listener();
      }
    },
    // A chunk that won't load leaves what it would draw as its source, as an add-on that is off.
    () => undefined,
  );
}

/** The loaded module `load` gives, once it has, or null; `load` starts only when `wanted`. */
export function useOnDemand<T>(load: (() => Promise<T>) | undefined, wanted = true): T | null {
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
  const value = useSyncExternalStore(subscribe, () => entry?.value ?? null);
  useEffect(() => {
    if (load && wanted) {
      start(load);
    }
  }, [load, wanted]);
  return wanted ? value : null;
}
