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

/** A colour deficiency a reader may have: no red, no green, or no blue cones. */
export type Deficiency = "protanopia" | "deuteranopia" | "tritanopia";

/** Machado, Oliveira and Fernandes' (2009) matrices, at full severity, on linear RGB. */
const SIMULATION: Record<Deficiency, number[][]> = {
  protanopia: [
    [0.152286, 1.052583, -0.204868],
    [0.114503, 0.786281, 0.099216],
    [-0.003882, -0.048116, 1.051998],
  ],
  deuteranopia: [
    [0.367322, 0.860646, -0.227968],
    [0.280085, 0.672501, 0.047413],
    [-0.01182, 0.04294, 0.968881],
  ],
  tritanopia: [
    [1.255528, -0.076749, -0.178779],
    [-0.078411, 0.930809, 0.147602],
    [0.004733, 0.691367, 0.3039],
  ],
};

const linear = (c: number) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);

/** CIE L*a*b* of a computed colour, as D65 sees it, from linear RGB. */
function lab(rgb: readonly number[]): [number, number, number] {
  const [r = 0, g = 0, b = 0] = rgb;
  const x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047;
  const y = 0.2126729 * r + 0.7151522 * g + 0.072175 * b;
  const z = (0.0193339 * r + 0.119192 * g + 0.9503041 * b) / 1.08883;
  const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : ((24389 / 27) * t + 16) / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}

/**
 * How far apart two computed colours look, as the distance between them in CIE L*a*b* (ΔE 1976):
 * about 2 is the least a person sees, and 20 or more is no doubt. With a `deficiency`, as a reader
 * with it sees them.
 */
export function distance(a: string, b: string, deficiency?: Deficiency): number {
  const seen = (colour: string) => {
    const rgb = channels(colour).map(linear);
    const matrix = deficiency && SIMULATION[deficiency];
    return lab(
      matrix
        ? matrix.map((row) =>
            Math.min(
              1,
              Math.max(
                0,
                row.reduce((sum, weight, at) => sum + weight * (rgb[at] ?? 0), 0),
              ),
            ),
          )
        : rgb,
    );
  };
  const [l1, a1, b1] = seen(a);
  const [l2, a2, b2] = seen(b);
  return Math.hypot(l1 - l2, a1 - a2, b1 - b2);
}
