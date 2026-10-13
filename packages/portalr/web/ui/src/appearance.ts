/**
 * The scheme a person chose for this browser: the system's, or light or dark, kept in
 * localStorage and set as the page's `data-theme`, which ui's tokens follow (portalr ADR-0009).
 * ui's `scheme.js` sets it again before the first paint of every page.
 */

import { useState } from "react";
import type { Appearance } from "./account-menu";

const KEY = "portalr-appearance";

/** The stored choice; the system's when there is none, or storage can't be read. */
function stored(): Appearance {
  try {
    const value = localStorage.getItem(KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

/** Set the page's scheme, and keep the choice where storage allows. */
function apply(appearance: Appearance) {
  const root = document.documentElement;
  if (appearance === "system") {
    delete root.dataset.theme;
  } else {
    root.dataset.theme = appearance;
  }
  try {
    localStorage.setItem(KEY, appearance);
  } catch {
    // Without storage the choice lasts as long as the page.
  }
}

/** The chosen scheme, and a way to choose another. */
export function useAppearance(): readonly [Appearance, (appearance: Appearance) => void] {
  const [appearance, setAppearance] = useState(stored);
  return [
    appearance,
    (chosen) => {
      apply(chosen);
      setAppearance(chosen);
    },
  ];
}
