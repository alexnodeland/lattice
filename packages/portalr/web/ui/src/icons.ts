/**
 * The kit's own icons (portalr ADR-0080): each a path on a 16-unit grid, drawn from scratch for
 * this product to its own grid and metaphors (no pack's artwork; checked against Lucide 1.55.0,
 * the set the UIs used before, by sampled-point distance after scaling), stroked by `Icon` at
 * 1.5 units with round terminals and joins, in the text's colour. A glyph is one `d` string, so
 * a new one costs its path and nothing more; the set ships whole, as one object, about a
 * kilobyte compressed. Metaphors are the kit's: a message is a note with a folded corner, a file
 * a leaf with a turned corner, a run a triangle, a rule a bolt, a workspace the mark's open
 * window. Chevrons and arrowheads share one angle and a slight optical curve.
 */

/** A glyph: the `d` of one path on the 16-unit grid, never a string from anywhere else. */
export type Glyph = string & { readonly [drawn]: true };
declare const drawn: unique symbol;

/** A path the kit drew, as a glyph. */
const g = (d: string) => d as Glyph;

const circle = "M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13";

export const glyphs = {
  // Arrows and chevrons, one head angle, a slight curve in a chevron
  arrowUp: g("M8 13V3M4 7l4-4 4 4"),
  arrowDown: g("M8 3v10M4 9l4 4 4-4"),
  arrowRight: g("M3 8h10M9 4l4 4-4 4"),
  arrowUpRight: g("M4 12l8-8M6 4h6v6"),
  arrowDownRight: g("M4 4l8 8M12 6v6H6"),
  arrowUpDown: g("M5 13V3M2.5 5.5 5 3l2.5 2.5M11 3v10M8.5 10.5 11 13l2.5-2.5"),
  chevronDown: g("M4.5 6.5 7.3 9.4a1 1 0 0 0 1.4 0l2.8-2.9"),
  chevronRight: g("M6.5 4.5 9.4 7.3a1 1 0 0 1 0 1.4l-2.9 2.8"),
  chevronLeft: g("M9.5 4.5 6.6 7.3a1 1 0 0 0 0 1.4l2.9 2.8"),
  // Marks
  plus: g("M8 3v10M3 8h10"),
  check: g("M3 8.5 6.5 12 13 4.5"),
  x: g("M5 5l6 6M11 5l-6 6"),
  circle: g(circle),
  square: g("M3 3h10v10H3z"),
  squareCheck: g("M3 3h10v10H3zM5.5 8l2 2 3.5-4"),
  info: g(`${circle}M8 7.5V11M8 5v.5`),
  circleAlert: g(`${circle}M8 5v3.5M8 11v.5`),
  triangleAlert: g("M8 2.5 14 13H2zM8 6.5v3M8 11.5v.5"),
  // Actions
  copy: g("M6 6h7v7H6zM10 6V3H3v7h3"),
  download: g("M8 2v8M5 7l3 3 3-3M3 13h10"),
  externalLink: g("M7 3H3v10h10V9M9 3h4v4M13 3 7 9"),
  refreshCw: g(
    "M13.5 8A5.5 5.5 0 0 0 3.8 4.5M2.5 8a5.5 5.5 0 0 0 9.7 3.5M3.8 1.5v3h3M12.2 14.5v-3h-3",
  ),
  logOut: g("M6 2.5H3v11h3M10 11l3-3-3-3M13 8H6"),
  menu: g("M2 4h12M2 8h12M2 12h12"),
  maximize: g("M3 3h10v10H3zM6.5 9.5 10 6M7.5 6H10v2.5"),
  minimize: g("M6 2v4H2M14 6h-4V2M10 14v-4h4M2 10h4v4"),
  maximize2: g("M3 7V3h4M13 9v4H9M3 3l4 4M13 13 9 9"),
  minimize2: g("M7 3v4H3M9 13V9h4M7 7 3 3M9 9l4 4"),
  wrapText: g("M2 4h12M2 8h8a2 2 0 0 1 0 4H9M2 12h4M10.5 10.5 9 12l1.5 1.5"),
  slidersHorizontal: g("M2 4h6M11 4h3M2 8h3M8 8h6M2 12h8M13 12h1M9.5 2.5v3M5.5 6.5v3M10.5 10.5v3"),
  play: g("M4 2.5v11L13 8z"),
  thumbsUp: g("M5 7v7H2V7zM5 7l3-5c1.5 0 2 1 2 2v3h3.5a1 1 0 0 1 1 1.2l-1 5a1 1 0 0 1-1 .8H5"),
  thumbsDown: g(
    "M11 9V2h3v7zM11 9l-3 5c-1.5 0-2-1-2-2V9H2.5a1 1 0 0 1-1-1.2l1-5a1 1 0 0 1 1-.8H11",
  ),
  // Things
  fileText: g("M4 2h5l3 3v9H4zM9 2v3h3M6 8h4M6 11h4"),
  fileUp: g("M4 2h5l3 3v9H4zM9 2v3h3M8 12V7M6 9l2-2 2 2"),
  scrollText: g("M3.5 2.5h9v11h-9zM3.5 5.5h9M6 8h4M6 10.5h2.5"),
  messageSquare: g("M2.5 3h11v8H6l-3.5 2.5V3z"),
  bot: g("M3 6h10v7H3zM8 3v3M6 9.5v.5M10 9.5v.5M1 9v1M15 9v1"),
  sparkles: g("M8 2l1.5 4.5L14 8l-4.5 1.5L8 14l-1.5-4.5L2 8l4.5-1.5zM13 2v2M12 3h2"),
  house: g("M2.5 7.5 8 3l5.5 4.5M4 7v6h8V7M7 13v-3h2v3"),
  building2: g("M3 14V3h7v11M10 7h3v7M2 14h12M5.5 6h2M5.5 9h2M5.5 12h2"),
  globe: g(`${circle}M1.5 8h13M8 1.5c2 2 2 11 0 13M8 1.5c-2 2-2 11 0 13`),
  database: g(
    "M8 5.5c3.3 0 5.5-.9 5.5-2s-2.2-2-5.5-2-5.5.9-5.5 2 2.2 2 5.5 2M2.5 3.5v9c0 1.1 2.2 2 5.5 2s5.5-.9 5.5-2v-9M2.5 8c0 1.1 2.2 2 5.5 2s5.5-.9 5.5-2",
  ),
  terminal: g("M2.5 3.5h11v9h-11zM5 6l2 2-2 2M8 10h3"),
  keyRound: g("M5.5 11.5a3 3 0 1 1 0-6 3 3 0 0 1 0 6M8 8.5l5.5-5.5M11.5 5l2 2"),
  usersRound: g(
    "M6 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5M2 13.5c0-2.5 1.8-4 4-4s4 1.5 4 4M11 2.8a2.5 2.5 0 0 1 0 4.7M14 13.5c0-2-1.2-3.5-3-3.9",
  ),
  puzzle: g("M3 3h4v1.5a1.5 1.5 0 0 0 3 0V3h3v3h-1.5a1.5 1.5 0 0 0 0 3H13v4H3z"),
  workflow: g(
    "M5 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5M8.5 9h5v4.5h-5zM5 7.5V10a1.5 1.5 0 0 0 1.5 1.5h2",
  ),
  zap: g("M9 1.5 3 9h4.5l-.5 5.5L13 7H8.5z"),
  route: g(
    "M3.5 13.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3M12.5 5.5a1.5 1.5 0 1 0 0-3 1.5 1.5 0 0 0 0 3M5 11c3.5-.5 2.5-5.5 6-6.5",
  ),
  coins: g("M8 14.5a6 6 0 1 0 0-12 6 6 0 0 0 0 12M5.5 8h5M8 5.5v5"),
  listChecks: g(
    "M2.5 4.5 3.5 5.5 5 3.5M2.5 8l1 1L5 7M2.5 11.5l1 1L5 10.5M7 4.5h6.5M7 8h6.5M7 11.5h6.5",
  ),
  wrench: g(
    "M2.5 13.5 8 8M8 8l1.5-1.5a3 3 0 0 1 3.8-3.8L11.5 4.5l1 1 1.8-1.8A3 3 0 0 1 9.5 7.5L8 8z",
  ),
} as const satisfies Record<string, Glyph>;
