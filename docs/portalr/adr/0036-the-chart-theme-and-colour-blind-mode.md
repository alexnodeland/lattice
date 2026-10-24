# ADR-0036: The chart theme: violet-led series, patterns only where marks touch, and a hook for colour-blind mode

**Status:** Accepted, amended 2026-10-23 (a line's markers only in the modes that need them)
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

The "$60 . 40" is not a monospace decimal point, as the audit took it to be. It is `tabular-nums` on Schibsted Grotesk: the face's tabular set gives the decimal point, comma, colon and percent sign the width of a digit (the point goes from 28 to 63 units at 100px, and the percent sign from 85 to 63), so the fault is the tabular numerals the audit asked for. The owner has since asked for a colour-blind mode, as a later change, which this one must leave a place for.

## Decision

- **One chart theme module,** `ui/src/chart-theme.tsx`, is what `BarChart`, `LineChart`, `DonutChart` and `Tracker` share:
  - The palette, and how a series is told apart beyond its hue, as helpers over custom properties (below).
  - The margins, and the axis and grid defaults: no axis lines or ticks, the muted ink, and very light horizontal gridlines only (`--chart-grid`).
  - The tooltip, on the surface menus float on (`popover`, now shared by `menu.tsx`): a title, then a row for each series with its mark, its name and its value.
  - The legend, and the number and date formatters: `formatNumber`, `formatDay` ("Oct 15") and `formatMoment` ("Oct 15 04:11", or "04:11"). Tables and tooltips keep a whole day or moment, `2026-10-15`; only an axis writes it shorter.
- **The palette is violet-led, with solid fills.** `--chart-1` is the brand violet, `--chart-2` a lighter tint of it, and `--chart-3` the one accent, a teal. Each is 3:1 or more on the paper and the surface in both schemes, and each pair is 20 or more apart, to CIEDE2000, to a reader with no deficiency and, simulated with Machado's matrices, with protanopia, deuteranopia or tritanopia, which tests hold. The floor of 20 is the bar this record sets, a few times what a person sees as a difference (about 1), and it is held under CIEDE2000, which weighs lightness, chroma and hue as the eye does, not CIE76's plain distance. The two violets differ mainly in lightness, and a test holds that too. The inks stay marks and never text (ADR-0021). The values, light and dark: `#6b2fa0` and `#c8aaf2`, `#a570e1` and `#864fc4`, `#0b8478` and `#347969`. The span bars of `TraceView` use `--chart-1`, so they take the theme's violet, and the colour-blind mode's blue, as the charts do.
- **A pattern is for marks that touch, or that are over a budget.** This replaces ADR-0021's pattern for every series and ADR-0027's dashed and dotted lines. By default:
  - Bars, lines and the donut's slices are solid, and a line is unbroken, with no markers: its points' markers are drawn only in colour-blind mode and under forced colours, where their shapes tell series apart (`--chart-marker-shown`). A point no line reaches, with no value on either side, keeps its marker always, or it wouldn't be drawn at all. (Amended 2026-10-23, from #214's audit, which found a single series's markers busy and read as dashes.)
  - A diverging chart's two halves meet at the baseline, so its second is hatched, and the Tracker's block over its share is hatched too.
  - What is folded into "Other" stays dotted in the muted ink.
  - Colour is never the only cue, as ADR-0021 asked: a series is named in the legend, and, where a chart has several, directly at its end; a diverging chart names its halves at its axis; and every chart's figures are the table under "Show the figures". The charts keep their aria text alternatives.
- **Colour-blind mode is a hook, and its control comes later.** `data-cvd` on the root element, or on any element to take it alone, with any value, as `data-theme` chooses the scheme. It sets custom properties and nothing else, so no chart changes; the table below lists them.
- **The status colours that follow** (muted red for failed, dead-lettered and error; amber for retrying and warnings) will use the same hook: they differ in lightness as well as hue, and always carry their shape and their word. This record does not change a status colour. The accent is a teal, chosen over the brand's magenta, which is only a little over 17 from the dark danger colour (`#ff9fb2`): a test holds it 20 or more from today's danger colour in both schemes and for every reader, and the amber to come is held to the same by the same test when it exists.
- **Numerals:** `Num` sets a figure with `tabular-nums` on each run of digits only, so figures in a column line up and a decimal point keeps its own width. The tooltip, the donut's total and legend, and Usage's headline use it. Ticks are proportional. `StatCard`, `TraceView` and `RunList` still set whole figures `tabular-nums`, and move to `Num` with their own restyle.
- **Labels are measured.** A chart's direct labels get the room that its widest, written whole where it fits within 30% of the chart's width, and otherwise cut to fit, takes in the chart's own font, measured with a canvas once the faces have loaded, and the value axis is as wide as its widest tick. A series on its own has no direct label: the legend and the caption name it.
- **The donut** has its total at its centre, and a legend in a grid of name, value and share, so a value sits beside its name.
- **Reading without a pointer.** A tooltip opens on hover, and the plot is hidden from assistive technology, so the figures under "Show the figures" are the keyboard and screen-reader equivalent: every value a tooltip gives is a cell of that table, and the donut's list gives each part's value and share, with separators read aloud only.
- **Tokens, not colours.** A chart writes no literal colour, dash or pattern: what it writes are tokens (`var(--muted)`, `var(--line)`, `var(--edge)`), and the series' own, which the mode changes.
- The screenshots pin the charts, wide and narrow, in each scheme and in colour-blind mode (`chart.screenshot.test.tsx`), as the gallery pins the frame.

### The colour-blind hook

| Property | By default | In `[data-cvd]` |
|---|---|---|
| `--chart-1`, `--chart-2`, `--chart-3` | violet, a lighter violet, teal | A blue, a vermillion (a yellow in dark) and a purple, from Okabe and Ito's hues, their lightness and saturation set to hold 3:1 in each scheme and 20 or more apart under each deficiency |
| `--chart-hatch` | 0, solid | `--chart-hatched`: every series past the first is hatched, at 45° and then 135° |
| `--chart-dash-1` to `--chart-dash-3` | none | none, `6 4`, then `2 3` |
| `--chart-marker-*` | A circle of 5px | 8px: a circle, a square, then a diamond |

A mark that touches another sets `--chart-hatch: var(--chart-hatched)` of its own, which agrees with the mode's, so no chart knows which mode it is drawn in. The colour-blind palette is held by the same tests, in the same bounds, so its claim is simulated rather than asserted; it rests on hue surviving and on the patterns being always on, not on hue alone. A control for the mode, and its place in the account menu, came later (see the amendment below).

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Palette | **Violet tints and one accent (chosen)** | A chart looks like the kit; the owner's direction | Three lightness steps of one hue need patterns' help in colour-blind mode |
| | Violet tints and the brand's magenta | An ink of the brand | Magenta is near the danger red in the dark scheme |
| | Cyan, magenta and violet, as before | Three hues | Reads as the brand's plates, not the kit |
| Patterns | **Where marks touch, and over a budget (chosen)** | Quiet charts; the pattern means something | Series that don't touch rest on the legend, direct labels and table, until the mode asks |
| | On every series after the first | Never colour alone, in the drawing | The busy hatching the audit found |
| Colour-blind mode | **Custom properties under `[data-cvd]` (chosen)** | Charts read tokens; one switch; tested | Markers set `x`, `y`, `width` and `rx` by CSS, which Chromium and Firefox take and Safari's support is to be checked when the control lands |
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
- Done since: the control for `data-cvd` (the amendment below), the status colours (ADR-0039), and `StatCard`, `TraceView` and `RunList`'s figures on `Num` (ADR-0039).

## Amendment, 2026-10-16: the control

The control this record deferred is built.

- **A switch in the account menu,** under **Colour**, which both UIs share (`Account`), worded "Colour-blind friendly charts" with the hint "Changes chart colours and adds patterns": the status colours are unchanged, so it is not called a mode to a person. It is a checkbox menu item, so its role is `menuitemcheckbox` and its state is announced as checked or not, and it is reached and toggled by the keyboard as the menu's other items are.
- **A setting of the browser,** kept as the scheme is: `portalr-colour-blind` in `localStorage`, `"on"` or absent, read and written inside `try`, so without storage the choice lasts as long as the page. It is not kept on the server, so it is not shared between a person's browsers. Both settings share one hook, `useStoredSetting`, which also hears a change made in another tab (a `storage` event), so every tab shows the choice and a later change starts from it; the scheme had the same gap, which the shared hook closes.
- **Applied before the first paint.** `scheme.js`, the script the UIs already load for the scheme, also sets `data-cvd` on the root, so the mode never flashes on after the page. The hook is unchanged: `data-cvd`, with any value, on the root.
- **Forced colours.** Under `forced-colors: active` every pattern, dash and marker shape is on as in the mode, whether it was chosen or not; a test holds the two token sets equal. Chromium forces text and backgrounds but leaves an SVG's fills and strokes as drawn, so a chart keeps its inks there and is told apart by the patterns, which a browser test on a real chart holds. Other engines may force the paints; then the patterns alone tell the series apart, which is why they are on.
- **Status colours** stay identical in the mode, as ADR-0039 records: they hold their floors to every reader on their own, and each is a shape and a word.
- The tests hold the palette, wired to `[data-cvd]`, to 3:1 on the paper and the surface and 20 or more apart under each simulated deficiency (existing), the storage and the pre-paint script (new), the menu item's role, state and key (new), forced colours (new), and the screenshots of charts and statuses with the mode on and off.
