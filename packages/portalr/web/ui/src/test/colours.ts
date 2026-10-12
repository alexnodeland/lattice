/** Which scheme the browser runs in, and the WCAG contrast of two computed colours. */

export const dark = matchMedia("(prefers-color-scheme: dark)").matches;

/** A token's value in the scheme the test runs in, as the browser computes it, within an element. */
export function token(name: string, within: Element = document.body): string {
  const probe = document.createElement("span");
  probe.style.color = `var(--${name})`;
  within.append(probe);
  const value = getComputedStyle(probe).color;
  probe.remove();
  return value;
}

/** A computed colour's channels, 0 to 1: `rgb()` counts to 255, and a mix's `color(srgb …)` to 1. */
function channels(colour: string): number[] {
  const scale = colour.startsWith("color(srgb") ? 1 : 255;
  return (colour.match(/[\d.]+/g) ?? []).slice(0, 3).map((part) => Number(part) / scale);
}

/** A computed colour's relative luminance, as WCAG defines it. */
export function luminance(colour: string): number {
  const [r, g, b] = channels(colour).map((c) =>
    c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * (r ?? 0) + 0.7152 * (g ?? 0) + 0.0722 * (b ?? 0);
}

export function contrast(a: string, b: string): number {
  const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return ((high ?? 0) + 0.05) / ((low ?? 0) + 0.05);
}
