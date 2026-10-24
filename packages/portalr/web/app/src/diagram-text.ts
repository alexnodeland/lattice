/**
 * A diagram's description, as artifactr's `describe` writes it for the agent (artifactr's
 * `excalidraw/render.py`), ported: the app's text alternative for a diagram, and the text its
 * revisions are compared by. The two are held equal by one fixture, which artifactr's Python
 * writes and both sides check (`packages/artifactr/schemas/excalidraw_descriptions.json`, portalr
 * ADR-0072). Its elements are read in JavaScript's order of an object's keys, which artifactr
 * reads them in too.
 *
 * It is pure, and never throws on data of any shape. The words in it are a diagram's, which
 * anyone in the workspace may write: they are shown as text, never as markup.
 */

/** The most characters a description holds. */
export const MAX_DESCRIPTION = 4_000;

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
type Element = Readonly<Record<string, Json>>;

const SHAPES = new Set(["rectangle", "ellipse", "diamond", "image", "embeddable", "iframe"]);
const LINES = new Set(["arrow", "line"]);
const BIDI = new Set([
  ..."\u061c\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069",
]);

/** Python's white space, which its `str.split()` splits on: JavaScript's `\s` isn't it. */
const SPACES = new Set([
  ...[0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680],
  ...Array.from({ length: 11 }, (_, at) => 0x2000 + at),
  ...[0x2028, 0x2029, 0x202f, 0x205f, 0x3000],
]);

const isObject = (value: Json | undefined): value is { [key: string]: Json } =>
  typeof value === "object" && value !== null && !Array.isArray(value);

/** A string as words, and anything else as none, as artifactr's `_words` has it. */
const wordsOf = (value: Json | undefined): string => (typeof value === "string" ? value : "");

/** Python's `" ".join(text.split())`. */
function collapsed(text: string): string {
  const words: string[] = [];
  let word = "";
  for (const character of text) {
    if (SPACES.has(character.codePointAt(0) ?? 0)) {
      if (word) words.push(word);
      word = "";
    } else {
      word += character;
    }
  }
  if (word) words.push(word);
  return words.join(" ");
}

/** Whether a character is said: not a control, a bidirectional control or a tag character. */
function shown(character: string): boolean {
  const code = character.codePointAt(0) ?? 0;
  const control = code <= 0x1f || (code >= 0x7f && code <= 0x9f);
  return !control && !BIDI.has(character) && !(code >= 0xe0000 && code <= 0xe007f);
}

/** Words written in the diagram, as words: on one line, at most 80 characters, quoted. */
function quote(text: Json | undefined): string {
  const kept = [...collapsed(wordsOf(text))].filter(shown).join("");
  const said = [...collapsed(kept)].slice(0, 80).join("");
  return `"${said.replaceAll("\\", "\\\\").replaceAll('"', '\\"')}"`;
}

/** The exact decimal digits of a finite double, and where its point is: `digits \u00d7 10^point`. */
function exact(value: number): { digits: string; point: number } {
  const view = new DataView(new ArrayBuffer(8));
  view.setFloat64(0, Math.abs(value));
  const bits = view.getBigUint64(0);
  const biased = Number((bits >> 52n) & 0x7ffn);
  const fraction = bits & 0xfffffffffffffn;
  const mantissa = biased === 0 ? fraction : fraction | (1n << 52n);
  const exponent = (biased === 0 ? 1 : biased) - 1075;
  if (exponent >= 0) return { digits: (mantissa << BigInt(exponent)).toString(), point: 0 };
  return { digits: (mantissa * 5n ** BigInt(-exponent)).toString(), point: exponent };
}

/** Python's `format(value, "g")`: six significant digits, rounded half to even, exactly. */
export function pyG(value: number): string {
  const sign = value < 0 || Object.is(value, -0) ? "-" : "";
  if (value === 0) return `${sign}0`;
  let { digits, point } = exact(value);
  digits = digits.replace(/^0+/, "");
  // The decimal exponent of its first digit.
  let first = digits.length - 1 + point;
  if (digits.length > 6) {
    const kept = BigInt(digits.slice(0, 6));
    const rest = digits.slice(6);
    const half = rest[0] === "5" && /^50*$/.test(rest);
    const up =
      rest[0] !== undefined && (rest[0] > "5" || (rest[0] === "5" && (!half || kept % 2n === 1n)));
    let rounded = (up ? kept + 1n : kept).toString();
    if (rounded.length > 6) {
      rounded = rounded.slice(0, 6);
      first += 1;
    }
    digits = rounded;
  }
  digits = digits.replace(/0+$/, "") || "0";
  if (first < -4 || first >= 6) {
    const mantissa = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits;
    const power = Math.abs(first).toString().padStart(2, "0");
    return `${sign}${mantissa}e${first < 0 ? "-" : "+"}${power}`;
  }
  if (first < 0) return `${sign}0.${"0".repeat(-first - 1)}${digits}`;
  const whole = digits.padEnd(first + 1, "0");
  const integer = whole.slice(0, first + 1);
  const decimals = whole.slice(first + 1);
  return `${sign}${integer}${decimals ? `.${decimals}` : ""}`;
}

const isNumber = (value: Json | undefined): value is number => typeof value === "number";

function box(elements: readonly Element[]): string | null {
  const edges: [number, number, number, number][] = [];
  for (const element of elements) {
    const { x, y } = element;
    const width = "width" in element ? element.width : 0;
    const height = "height" in element ? element.height : 0;
    if (isNumber(x) && isNumber(y) && isNumber(width) && isNumber(height)) {
      const edge: [number, number, number, number] = [x, y, x + width, y + height];
      if (edge.every(Number.isFinite)) edges.push(edge);
    }
  }
  if (edges.length === 0) return null;
  const left = Math.min(...edges.map((e) => e[0]));
  const top = Math.min(...edges.map((e) => e[1]));
  const right = Math.max(...edges.map((e) => e[2]));
  const bottom = Math.max(...edges.map((e) => e[3]));
  return `x ${pyG(left)} to ${pyG(right)}, y ${pyG(top)} to ${pyG(bottom)}`;
}

function cut(text: string): string {
  const characters = [...text];
  if (characters.length <= MAX_DESCRIPTION) return text;
  const more = "\n… (cut: read the diagram for the rest)";
  return characters.slice(0, MAX_DESCRIPTION - [...more].length).join("") + more;
}

/** Describe a diagram's live elements, as the agent and assistive technology read it. */
export function describe(name: unknown, elements: unknown): string {
  const all = isObject(elements as Json) ? (elements as { [key: string]: Json }) : {};
  const live = new Map<string, Element>();
  for (const [key, element] of Object.entries(all)) {
    if (isObject(element) && !element.isDeleted) live.set(key, element);
  }
  const labels = new Map<string, string>();
  for (const element of live.values()) {
    const container = element.containerId;
    if (element.type === "text" && typeof container === "string") {
      labels.set(container, quote(element.text));
    }
  }
  const named = (key: string) => (labels.has(key) ? `${key} ${labels.get(key)}` : key);
  const bound = (binding: Json | undefined) => {
    const key = isObject(binding) ? binding.elementId : undefined;
    return typeof key === "string" && live.has(key) ? key : null;
  };
  const frames: string[] = [];
  const shapes: string[] = [];
  const arrows: string[] = [];
  const texts: string[] = [];
  for (const [key, element] of live) {
    const kind = wordsOf(element.type);
    if (kind === "frame" || kind === "magicframe") {
      const title = element.name;
      frames.push(`- ${typeof title === "string" && title ? `${key} ${quote(title)}` : key}`);
    } else if (SHAPES.has(kind)) {
      shapes.push(`- ${kind} ${named(key)}`);
    } else if (LINES.has(kind)) {
      const start = bound(element.startBinding);
      const end = bound(element.endBinding);
      const label = labels.get(wordsOf(element.id));
      const via = label ? `--${label}-->` : "-->";
      const left = start ? named(start) : "(free)";
      const right = end ? named(end) : "(free)";
      arrows.push(`- ${kind} ${key}: ${left} ${via} ${right}`);
    } else if (
      kind === "text" &&
      (element.containerId === undefined || element.containerId === null)
    ) {
      texts.push(`- ${quote(element.text)}`);
    }
  }
  const lines = [`Diagram ${quote(typeof name === "string" ? name : "")}: ${live.size} elements`];
  const bounds = box([...live.values()]);
  if (bounds !== null) lines.push(`Bounds: ${bounds}`);
  for (const [title, part] of [
    ["Frames", frames],
    ["Shapes", shapes],
    ["Arrows", arrows],
    ["Text", texts],
  ] as const) {
    if (part.length > 0) lines.push(`${title} (${part.length}):`, ...part);
  }
  return cut(lines.join("\n"));
}
