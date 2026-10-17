/**
 * The scheme a person chose for this browser: the system's, or light or dark, kept in
 * localStorage and set as the page's `data-theme`, which ui's tokens follow (portalr ADR-0009).
 * ui's `scheme.js` sets it again before the first paint of every page, and another tab's change is
 * followed (`useStoredSetting`).
 */

import type { Appearance } from "./account-menu";
import { useStoredSetting } from "./stored-setting";

const SETTING = {
  key: "portalr-appearance",
  parse: (stored: string | null): Appearance =>
    stored === "light" || stored === "dark" ? stored : "system",
  serialise: (appearance: Appearance) => appearance,
  apply: (appearance: Appearance) => {
    const root = document.documentElement;
    if (appearance === "system") {
      delete root.dataset.theme;
    } else {
      root.dataset.theme = appearance;
    }
  },
};

/** The chosen scheme, and a way to choose another. */
export function useAppearance(): readonly [Appearance, (appearance: Appearance) => void] {
  return useStoredSetting(SETTING);
}
