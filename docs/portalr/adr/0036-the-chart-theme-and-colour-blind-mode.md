# ADR-0036: The chart theme: violet-led series, patterns only where marks touch, and a hook for colour-blind mode

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland
**Amends:** the chart rule of [ADR-0021](0021-the-areas-on-the-frame-and-what-admin-needs.md) and [ADR-0027](0027-feedback-and-evaluations.md), and the tokens of [ADR-0019](0019-the-kits-look.md)

## Context

A design audit of about 200 screenshots (issue 214) found the charts the most visibly unfinished part of `ui`:

- End-labels were clipped or truncated ("Thumbs dowr", "95th percenti…") or floated alone ("Spend"). The room for them was a guess of 7px a character.
- A value axis wrapped its unit under its figure ("0.24" over "s"), the thumbs-down half of Feedback's axis was unlabelled, and a figure was set as "$60 . 40".
- Lines wore a marker per point, in a shape and a dash per series, and bars wore a hatch, all at once.
- The donut had no total, its legend put each value at the far end of its row, and its tooltip was a box of its own, unlike a menu.
- Each chart wrote its own margins, grid, tick and tooltip. The palette was cyan, magenta and violet, so a chart looked like the marks and not like the kit.

The "$60 . 40" is not a monospace decimal point, as the audit took it to be. It is `tabular-nums` on Schibsted Grotesk: the face's tabular set widens the decimal point, comma, colon and percent sign to the width of a digit (28 against 63 units at 100px), so the fault is the tabular numerals the audit asked for. The owner has since asked for a colour-blind mode, as a later change, which this one must leave a place for.

## Decision

- **One chart theme module,** `ui/src/chart-theme.tsx`, is what `BarChart`, `LineChart`, `DonutChart` and `Tracker` share:
  - The palette, and how a series is told apart beyond its hue, as helpers over custom properties (below).
  - The margins, and the axis and grid defaults: no axis lines or ticks, the muted ink, and very light horizontal gridlines only (`--chart-grid`).
  - The tooltip, on the surface menus float on (`popover`, now shared by `menu.tsx`): a title, then a row for each series with its mark, its name and its value.
  - The legend, and the number and date formatters: `formatNumber`, `formatDay` ("Oct 15") and `formatMoment` ("Oct 15 04:11", or "04:11"). Tables and tooltips keep a whole day or moment, `2026-10-15`; only an axis writes it shorter.
- **The palette is violet-led, with solid fills.** `--chart-1` is the brand violet, `--chart-2` a lighter tint of it, and `--chart-3` the one accent, the brand's magenta. Each is 3:1 or more on the paper and the surface in both schemes, and each pair is told apart (CIE L\*a\*b\* distance of 18 or more) to a reader with no deficiency and, simulated, with protanopia, deuteranopia or tritanopia (17 or more), which tests hold. The inks stay marks and never text (ADR-0021).
- **A pattern is for marks that touch, or that are over a budget.** This replaces ADR-0021's pattern for every series and ADR-0027's dashed and dotted lines. By default:
  - Bars, lines and the donut's slices are solid, and a line is unbroken, its markers small circles.
  - A diverging chart's two halves meet at the baseline, so its second is hatched, and the Tracker's block over its share is hatched too.
  - What is folded into "Other" stays dotted in the muted ink.
  - Colour is never the only cue, as ADR-0021 asked: a series is named in the legend, and, where a chart has several, directly at its end; a diverging chart names its halves at its axis; and every chart's figures are the table under "Show the figures". The charts keep their aria text alternatives.
- **Colour-blind mode is a hook, and its control comes later.** `data-cvd` on the root element, or on any element to take it alone, with any value, as `data-theme` chooses the scheme. It sets custom properties and nothing else, so no chart changes; the table below lists them.
- **The status colours that follow** (muted red for failed, dead-lettered and error; amber for retrying and warnings) will use the same hook: they differ in lightness as well as hue, and always carry their shape and their word. This record does not change a status colour. The accent is the brand's magenta, so the status work must keep its red and amber clear of it in hue and in lightness.
- **Numerals:** `Num` sets a figure with `tabular-nums` on each run of digits only, so figures in a column line up and a decimal point keeps its own width. The tooltip, the donut's total and legend, and Usage's headline use it. Ticks are proportional. `StatCard`, `TraceView` and `RunList` still set whole figures `tabular-nums`, and move to `Num` with their own restyle.
- **Labels are measured.** A chart's direct labels get the room that its widest, cut to 14 characters, takes in the chart's own font, measured with a canvas once the faces have loaded, and the value axis is as wide as its widest tick. A series on its own has no direct label: the legend and the caption name it.
- **The donut** has its total at its centre, and a legend in a grid of name, value and share, so a value sits beside its name.
- The screenshots pin the charts, wide and narrow, in each scheme and in colour-blind mode (`chart.screenshot.test.tsx`), as the gallery pins the frame.

### The colour-blind hook

| Property | By default | In `[data-cvd]` |
|---|---|---|
| `--chart-1`, `--chart-2`, `--chart-3` | violet, a lighter violet, magenta | A blue, a vermillion and a reddish purple, from Okabe and Ito's set, lightened or darkened to hold 3:1 in each scheme |
| `--chart-hatch` | 0, solid | `--chart-hatched`: every series past the first is hatched, at 45° and then 135° |
| `--chart-dash-1` to `--chart-dash-3` | none | none, `6 4`, then `2 3` |
| `--chart-marker-*` | A circle of 5px | 8px: a circle, a square, then a diamond |

A mark that touches another sets `--chart-hatch: var(--chart-hatched)` of its own, which agrees with the mode's, so no chart knows which mode it is drawn in. The colour-blind palette is held by the same tests, in the same bounds, so its claim is simulated rather than asserted; it rests on hue surviving and on the patterns being always on, not on hue alone. A control for the mode, and its place in the account menu, come later.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Palette | **Violet tints and one accent (chosen)** | A chart looks like the kit; the owner's direction | Three lightness steps of one hue need patterns' help in colour-blind mode |
| | Cyan, magenta and violet, as before | Three hues | Reads as the brand's plates, not the kit |
| Patterns | **Where marks touch, and over a budget (chosen)** | Quiet charts; the pattern means something | Series that don't touch rest on the legend, direct labels and table, until the mode asks |
| | On every series after the first | Never colour alone, in the drawing | The busy hatching the audit found |
| Colour-blind mode | **Custom properties under `[data-cvd]` (chosen)** | Charts read tokens; one switch; tested | Markers use CSS geometry properties, which need a current browser |
| | A theme object chosen in JavaScript | Plain code | Every chart knows the mode; two places to change |
| Numerals | **`Num`: tabular digits only (chosen)** | Aligned and tight | A component where a class was |
| | `tabular-nums` on the whole figure | One class | "$60 . 40" |
| | Fragment Mono for figures | Tabular, and tight | Two faces in a row of figures |
| Label room | **Measure the text (chosen)** | Exact in any face | A measure after the faces load |
| | A guess of 7px a character | None to write | Clipped "Thumbs dowr" |

## Consequences

- Easier: a chart's colour, marker or pattern changes in `tokens.css` alone, and a colour-blind control needs only to set an attribute.
- Easier: a series' contrast and separation fail a test in the scheme and the mode that break them.
- Harder: a chart that wants its own mark must add it to the theme, not to itself.
- To revisit: the control for `data-cvd`, and the status colours' tokens, in their own changes; `StatCard`, `TraceView` and `RunList`'s figures, with `Num`.
