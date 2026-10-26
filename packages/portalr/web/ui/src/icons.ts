/**
 * The kit's own icons (portalr ADR-0080): each a path on a 16-unit grid, drawn for this product
 * and no pack's, stroked by `Icon` at 1.5 units with round terminals and joins, in the text's
 * colour. A glyph is one `d` string, so a new one costs its path and nothing more. Metaphors are
 * the kit's: a thread is a folded note, an artifact a leaf with a turned corner, a workspace the
 * mark's open window, a run a triangle, a rule a bolt. Arrowheads and chevrons share one angle.
 */

/** A glyph: the `d` of one path on the 16-unit grid. */
export type Glyph = string;

const circle = "M8 14.5a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13";

export const glyphs = {
  // Arrows and chevrons, one head angle
  arrowUp: "M8 13V3M4 7l4-4 4 4",
  arrowDown: "M8 3v10M4 9l4 4 4-4",
  arrowRight: "M3 8h10M9 4l4 4-4 4",
  arrowUpRight: "M4 12l8-8M6 4h6v6",
  arrowDownRight: "M4 4l8 8M12 6v6H6",
  arrowUpDown: "M5 13V3M2.5 5.5 5 3l2.5 2.5M11 3v10M8.5 10.5 11 13l2.5-2.5",
  chevronDown: "M4 6l4 4 4-4",
  chevronRight: "M6 4l4 4-4 4",
  chevronLeft: "M10 4 6 8l4 4",
  // Marks
  plus: "M8 3v10M3 8h10",
  check: "M3 8.5 6.5 12 13 4.5",
  x: "M4 4l8 8M12 4l-8 8",
  circle,
  square: "M3 3h10v10H3z",
  squareCheck: "M3 3h10v10H3zM5.5 8l2 2 3.5-4",
  info: `${circle}M8 7.5V11M8 5v.5`,
  circleAlert: `${circle}M8 5v3.5M8 11v.5`,
  triangleAlert: "M8 2.5 14 13H2zM8 6.5v3M8 11.5v.5",
  // Actions
  copy: "M6 6h7v7H6zM10 6V3H3v7h3",
  download: "M8 2v8M5 7l3 3 3-3M3 13h10",
  externalLink: "M7 3H3v10h10V9M9 3h4v4M13 3 7 9",
  refreshCw:
    "M13.5 8A5.5 5.5 0 0 0 3.8 4.5M2.5 8a5.5 5.5 0 0 0 9.7 3.5M3.8 1.5v3h3M12.2 14.5v-3h-3",
  logOut: "M6 2.5H3v11h3M10 11l3-3-3-3M13 8H6",
  menu: "M2 4h12M2 8h12M2 12h12",
  maximize: "M2 6V2h4M10 2h4v4M14 10v4h-4M6 14H2v-4",
  minimize: "M6 2v4H2M14 6h-4V2M10 14v-4h4M2 10h4v4",
  maximize2: "M9 2h5v5M14 2 9 7M7 14H2V9M2 14l5-5",
  minimize2: "M14 7H9V2M9 7l5-5M2 9h5v5M7 9l-5 5",
  wrapText: "M2 4h12M2 8h8a2 2 0 0 1 0 4H9M2 12h4M10.5 10.5 9 12l1.5 1.5",
  slidersHorizontal: "M2 4h6M11 4h3M2 8h3M8 8h6M2 12h8M13 12h1M9.5 2.5v3M5.5 6.5v3M10.5 10.5v3",
  play: "M4 2.5v11L13 8z",
  thumbsUp: "M5 7v7H2V7zM5 7l3-5c1.5 0 2 1 2 2v3h3.5a1 1 0 0 1 1 1.2l-1 5a1 1 0 0 1-1 .8H5",
  thumbsDown: "M11 9V2h3v7zM11 9l-3 5c-1.5 0-2-1-2-2V9H2.5a1 1 0 0 1-1-1.2l1-5a1 1 0 0 1 1-.8H11",
  // Things
  fileText: "M4 2h5l3 3v9H4zM9 2v3h3M6 8h4M6 11h4",
  fileUp: "M4 2h5l3 3v9H4zM9 2v3h3M8 12V7M6 9l2-2 2 2",
  scrollText:
    "M4 2h9v10a2 2 0 0 1-2 2H3a1.5 1.5 0 0 1-1.5-1.5V11H11M4 2a2 2 0 0 0-2 2v2h2M6.5 5h4M6.5 8h4",
  messageSquare: "M2.5 3h11v8H6l-3.5 2.5V3z",
  bot: "M3 6h10v7H3zM8 3v3M6 9.5v.5M10 9.5v.5M1 9v1M15 9v1",
  sparkles: "M8 2l1.5 4.5L14 8l-4.5 1.5L8 14l-1.5-4.5L2 8l4.5-1.5zM13 2v2M12 3h2",
  house: "M2.5 7.5 8 3l5.5 4.5M4 7v6h8V7M7 13v-3h2v3",
  building2: "M3 14V3h7v11M10 7h3v7M2 14h12M5.5 6h2M5.5 9h2M5.5 12h2",
  globe: `${circle}M1.5 8h13M8 1.5c2 2 2 11 0 13M8 1.5c-2 2-2 11 0 13`,
  database:
    "M8 5.5c3.3 0 5.5-.9 5.5-2s-2.2-2-5.5-2-5.5.9-5.5 2 2.2 2 5.5 2M2.5 3.5v9c0 1.1 2.2 2 5.5 2s5.5-.9 5.5-2v-9M2.5 8c0 1.1 2.2 2 5.5 2s5.5-.9 5.5-2",
  terminal: "M3 4l4 4-4 4M8 12h5",
  keyRound: "M5.5 11.5a3 3 0 1 1 0-6 3 3 0 0 1 0 6M8 8.5l5.5-5.5M11.5 5l2 2",
  usersRound:
    "M6 7.5a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5M2 13.5c0-2.5 1.8-4 4-4s4 1.5 4 4M11 2.8a2.5 2.5 0 0 1 0 4.7M14 13.5c0-2-1.2-3.5-3-3.9",
  puzzle: "M3 3h4v1.5a1.5 1.5 0 0 0 3 0V3h3v3h-1.5a1.5 1.5 0 0 0 0 3H13v4H3z",
  workflow: "M2 2h5v5H2zM9 9h5v5H9zM7 4.5h2.5a1 1 0 0 1 1 1V9",
  zap: "M9 1.5 3 9h4.5l-.5 5.5L13 7H8.5z",
  route:
    "M4 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4M12 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4M6 11h3.5a2 2 0 0 0 0-4H10",
  coins: "M6 10.5a4 4 0 1 0 0-8 4 4 0 0 0 0 8M9.8 7.1A4 4 0 1 1 6 13.5",
  listChecks: "M2.5 4 3.5 5 5.5 3M8 4h6M2.5 9l1 1 2-2M8 9h6M8 14h6M2.5 14l1 1 2-2",
  wrench: "M10 2.5a3.5 3.5 0 0 0-4.3 4.3L2 10.5 5.5 14l3.7-3.7A3.5 3.5 0 0 0 13.5 6l-2 2-2-2z",
} as const satisfies Record<string, Glyph>;

/** The name of a glyph the kit has. */
export type GlyphName = keyof typeof glyphs;
