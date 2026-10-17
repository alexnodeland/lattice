/**
 * Colour-blind mode, as a person chose it for this browser: kept in localStorage, as the scheme
 * is, and set as the page's `data-cvd`, which ui's tokens follow, so the charts take the palette
 * and the patterns that hold for every reader (portalr ADR-0036). ui's `scheme.js` sets it again
 * before the first paint of every page, so the mode never flashes on after the page.
 */

import { useState } from "react";

const KEY = "portalr-colour-blind";

/** Whether it was chosen; off when there is no choice, or storage can't be read. */
function stored(): boolean {
  try {
    return localStorage.getItem(KEY) === "on";
  } catch {
    return false;
  }
}

/** Set the page's mode, and keep the choice where storage allows. */
function apply(on: boolean) {
  const root = document.documentElement;
  if (on) {
    root.dataset.cvd = "";
  } else {
    delete root.dataset.cvd;
  }
  try {
    if (on) {
      localStorage.setItem(KEY, "on");
    } else {
      localStorage.removeItem(KEY);
    }
  } catch {
    // Without storage the choice lasts as long as the page.
  }
}

/** Whether colour-blind mode is on, and a way to turn it on or off. */
export function useColourBlind(): readonly [boolean, (on: boolean) => void] {
  const [on, setOn] = useState(stored);
  return [
    on,
    (chosen) => {
      apply(chosen);
      setOn(chosen);
    },
  ];
}
