/**
 * The chart theme's colours as a renderer that computes with colours needs them: resolved from the
 * tokens to the colours the browser draws, in the scheme and the mode a chart is in. A renderer
 * that only writes `var(--chart-1)`, as the kit's charts do, follows the tokens of itself; one
 * that draws on a canvas, or derives a colour from another, can't read a custom property, so it
 * takes these, which are read again whenever the scheme, colour-blind mode or forced colours
 * change, on the page's root or on any element round the chart (portalr ADR-0047). They are read
 * only where a renderer may use them, and after the first render, which has none.
 */

import { type RefObject, useEffect, useState } from "react";

/** The tokens a chart draws with, by name. */
const NAMES = ["chart-1", "chart-2", "chart-3", "muted", "chart-grid", "surface", "fg"] as const;

/** A chart's colours, each a token's as the browser computes it, and the modes it is drawn in. */
export interface ChartTokens {
  readonly colours: Readonly<Record<(typeof NAMES)[number], string>>;
  /** Whether colour-blind mode is on where the chart is: patterns on, as `data-cvd` asks. */
  readonly cvd: boolean;
  /** Whether forced colours are on: patterns on, and the system's colours. */
  readonly forced: boolean;
}

/** The attributes that change a token, on the root or round a chart: the scheme, and colour-blind mode. */
const ATTRIBUTES = ["data-theme", "data-cvd"];

/** The media that change a token: the system's scheme, and forced colours. */
const MEDIA = ["(prefers-color-scheme: dark)", "(forced-colors: active)"];

/** The tokens as the browser computes them inside `within`, so a mode set on it alone counts. */
function resolve(within: Element): ChartTokens {
  const probe = document.createElement("span");
  within.append(probe);
  const colours = Object.fromEntries(
    NAMES.map((name) => {
      probe.style.color = `var(--${name})`;
      return [name, getComputedStyle(probe).color];
    }),
  ) as ChartTokens["colours"];
  probe.remove();
  return {
    colours,
    cvd: within.closest("[data-cvd]") !== null,
    forced: matchMedia("(forced-colors: active)").matches,
  };
}

/**
 * The chart theme's colours inside `ref`'s element, once it is drawn, while `wanted`; null before
 * then, and while not. Read again when the scheme or colour-blind mode change on any element, as
 * on the root or one round the chart, or the system's scheme or forced colours do.
 */
export function useChartTokens(
  ref: RefObject<Element | null>,
  wanted: boolean,
): ChartTokens | null {
  const [tokens, setTokens] = useState<ChartTokens | null>(null);
  useEffect(() => {
    if (!wanted) {
      setTokens(null);
      return;
    }
    const read = () => setTokens(resolve(ref.current ?? document.documentElement));
    read();
    // The whole page, since the mode that counts may be set on any element round the chart.
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ATTRIBUTES,
      subtree: true,
    });
    const media = MEDIA.map((query) => matchMedia(query));
    for (const each of media) {
      each.addEventListener("change", read);
    }
    return () => {
      observer.disconnect();
      for (const each of media) {
        each.removeEventListener("change", read);
      }
    };
  }, [ref, wanted]);
  return tokens;
}
