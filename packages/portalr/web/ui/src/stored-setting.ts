/**
 * A setting a person chose for this browser, in localStorage, applied to the page when it is read
 * and when it changes, and followed across tabs: a change in another tab is heard as a `storage`
 * event, so every tab of the browser shows the choice and a later change in any of them starts
 * from it, not from what that tab last knew. Storage that can't be read or written is the
 * fallback's, and the choice lasts as long as the page (portalr ADR-0009, ADR-0036).
 */

import { useEffect, useState } from "react";

interface Setting<V> {
  /** The localStorage key. */
  readonly key: string;
  /** The value from what is stored, which is `null` when nothing is. */
  readonly parse: (stored: string | null) => V;
  /** What to store for a value, or `null` to store nothing. */
  readonly serialise: (value: V) => string | null;
  /** Put the value on the page. */
  readonly apply: (value: V) => void;
}

function read<V>(setting: Setting<V>): V {
  try {
    return setting.parse(localStorage.getItem(setting.key));
  } catch {
    return setting.parse(null);
  }
}

/** The setting's value, and a way to change it, here and, through storage, in every tab. */
export function useStoredSetting<V>(setting: Setting<V>): readonly [V, (value: V) => void] {
  const [value, setValue] = useState(() => read(setting));
  useEffect(() => {
    const heard = (event: StorageEvent) => {
      // A key of null is the storage cleared.
      if (event.key === setting.key || event.key === null) {
        const next = setting.parse(event.newValue);
        setting.apply(next);
        setValue(next);
      }
    };
    window.addEventListener("storage", heard);
    return () => window.removeEventListener("storage", heard);
  }, [setting]);
  return [
    value,
    (chosen) => {
      setting.apply(chosen);
      try {
        const stored = setting.serialise(chosen);
        if (stored === null) {
          localStorage.removeItem(setting.key);
        } else {
          localStorage.setItem(setting.key, stored);
        }
      } catch {
        // Without storage the choice lasts as long as the page.
      }
      setValue(chosen);
    },
  ];
}
