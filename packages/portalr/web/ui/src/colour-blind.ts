/**
 * Colour-blind friendly charts, as a person chose them for this browser: kept in localStorage, as
 * the scheme is, and set as the page's `data-cvd`, which ui's tokens follow, so the charts take the
 * palette and the patterns that hold for every reader (portalr ADR-0036). ui's `scheme.js` sets it
 * again before the first paint of every page, so it never flashes on after the page, and another
 * tab's change is followed (`useStoredSetting`).
 */

import { useStoredSetting } from "./stored-setting";

const SETTING = {
  key: "portalr-colour-blind",
  parse: (stored: string | null) => stored === "on",
  serialise: (on: boolean) => (on ? "on" : null),
  apply: (on: boolean) => {
    if (on) {
      document.documentElement.dataset.cvd = "";
    } else {
      delete document.documentElement.dataset.cvd;
    }
  },
};

/** Whether colour-blind friendly charts are on, and a way to turn them on or off. */
export function useColourBlind(): readonly [boolean, (on: boolean) => void] {
  return useStoredSetting(SETTING);
}
