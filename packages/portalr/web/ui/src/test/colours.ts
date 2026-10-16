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

/**
 * A computed colour's channels, 0 to 1: `rgb()` counts to 255, and a mix's `color(srgb …)` to 1.
 * Anything else, a colour with alpha, or in another space, such as `lab()` or `oklch()`, throws,
 * where reading its numbers as sRGB would only give a wrong answer.
 */
function channels(colour: string): number[] {
  const srgb = colour.startsWith("color(srgb");
  const plain = /^rgb\(\s*[\d.]+[ ,]+[\d.]+[ ,]+[\d.]+\s*\)$/.test(colour);
  if (!(plain || (srgb && !colour.includes("/")))) {
    throw new Error(`a colour that is not opaque sRGB: ${colour}`);
  }
  const scale = srgb ? 1 : 255;
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

/** CIE L*a*b* of linear RGB, as D65 sees it. */
function lab(rgb: readonly number[]): [number, number, number] {
  const [r = 0, g = 0, b = 0] = rgb;
  const x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / 0.95047;
  const y = 0.2126729 * r + 0.7151522 * g + 0.072175 * b;
  const z = (0.0193339 * r + 0.119192 * g + 0.9503041 * b) / 1.08883;
  const f = (t: number) => (t > 216 / 24389 ? Math.cbrt(t) : ((24389 / 27) * t + 16) / 116);
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))];
}

const radians = (degrees: number) => (degrees * Math.PI) / 180;
const degrees = (rad: number) => ((rad * 180) / Math.PI + 360) % 360;

/** CIEDE2000, Sharma, Wu and Dalal's (2005) formulation, of two L*a*b* colours. */
export function deltaE2000(
  [l1, a1, b1]: readonly [number, number, number],
  [l2, a2, b2]: readonly [number, number, number],
): number {
  const meanChroma = (Math.hypot(a1, b1) + Math.hypot(a2, b2)) / 2;
  const g = 0.5 * (1 - Math.sqrt(meanChroma ** 7 / (meanChroma ** 7 + 25 ** 7)));
  const a1p = (1 + g) * a1;
  const a2p = (1 + g) * a2;
  const c1 = Math.hypot(a1p, b1);
  const c2 = Math.hypot(a2p, b2);
  const h1 = c1 === 0 ? 0 : degrees(Math.atan2(b1, a1p));
  const h2 = c2 === 0 ? 0 : degrees(Math.atan2(b2, a2p));
  const dL = l2 - l1;
  const dC = c2 - c1;
  let dh = 0;
  if (c1 * c2 !== 0) {
    dh = h2 - h1;
    if (dh > 180) {
      dh -= 360;
    } else if (dh < -180) {
      dh += 360;
    }
  }
  const dH = 2 * Math.sqrt(c1 * c2) * Math.sin(radians(dh / 2));
  const meanL = (l1 + l2) / 2;
  const meanC = (c1 + c2) / 2;
  let meanH = h1 + h2;
  if (c1 * c2 !== 0) {
    meanH = Math.abs(h1 - h2) > 180 ? (h1 + h2 + (h1 + h2 < 360 ? 360 : -360)) / 2 : (h1 + h2) / 2;
  }
  const t =
    1 -
    0.17 * Math.cos(radians(meanH - 30)) +
    0.24 * Math.cos(radians(2 * meanH)) +
    0.32 * Math.cos(radians(3 * meanH + 6)) -
    0.2 * Math.cos(radians(4 * meanH - 63));
  const rotation =
    -Math.sin(radians(2 * 30 * Math.exp(-(((meanH - 275) / 25) ** 2)))) *
    2 *
    Math.sqrt(meanC ** 7 / (meanC ** 7 + 25 ** 7));
  const sl = 1 + (0.015 * (meanL - 50) ** 2) / Math.sqrt(20 + (meanL - 50) ** 2);
  const sc = 1 + 0.045 * meanC;
  const sh = 1 + 0.015 * meanC * t;
  return Math.sqrt(
    (dL / sl) ** 2 + (dC / sc) ** 2 + (dH / sh) ** 2 + rotation * (dC / sc) * (dH / sh),
  );
}

/**
 * How far apart two computed colours look, as CIEDE2000 gives it: about 1 is the least a person
 * sees, and 20 or more, the floor the charts hold their series to, is no doubt. With a `deficiency`,
 * as a reader with it sees them.
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
  return deltaE2000(seen(a), seen(b));
}
