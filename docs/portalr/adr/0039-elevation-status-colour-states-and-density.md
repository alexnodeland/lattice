# ADR-0039: Elevation, status colours, alerts and placeholders, and admin's compact density

**Status:** Accepted, amended by [ADR-0080](0080-ink-on-paper-the-products-visual-language.md) (elevation and the badge's pill)
**Date:** 2026-10-16
**Deciders:** Alex Nodeland
**Amends:** the look and statuses of [ADR-0019](0019-the-kits-look.md), and the budget badges of [ADR-0021](0021-the-areas-on-the-frame-and-what-admin-needs.md)

## Context

The UI polish pass (issue 214) left four faults after the charts and the controls:

- Dialogs had a hairline border, no shadow and a flat scrim, and the shadow a menu had was invisible on the dark paper.
- Page headers and cards had no one rhythm: titles in the face's heaviest weight, figures that didn't line up, cards of different heights in a row, and a dead gutter at the right of a wide screen.
- Failed, dead-lettered and error were as neutral as succeeded: a failed run was a square and a word, and nothing else. The danger colour was a separate pink.
- Messages were prose in a paragraph; there were no loading placeholders; a list of workspaces, one of people with access, and one of threads were three idioms; and admin's tables and logs were as roomy as the app's lists.

## Decision

- **Elevation is three shadows from one colour.** `--shadow-color` is a faint violet in light and black, heavier, in dark, where a faint shadow is not seen. `shadow-raised` is a card's, `shadow-md` a menu's and a tooltip's, and `shadow-lg` a dialog's and the drawer's. A dialog's scrim blurs what is behind it by 3px and fades in with the dialog's own fade and scale; each is off where motion is reduced.
- **A type scale** (`type.ts`): page, section, label, a quiet label, meta, note and figure. A component takes its text from it; text that still sets its own size and weight is moved onto it as its page is restyled. Weights stop at 600: the face's 700 is heavy beside Fragment Mono. A page's line about it is the body's size, a card's figure is tabular on its digits only (`Num`), cards in a row are as tall as the tallest with their action at their foot, and a page's content is no wider than `--page-width` (75rem) and is centred, so a wide screen has no gutter at its right. `StatCard`, `TraceView` and `RunList` take `Num`, which ADR-0036 left for here.
- **Status has colour, as a mark.** `--status-failed` is a rose red (`#8a0f2c` light, `#f391b1` dark) and `--status-warn` a gold (`#9c821c`, `#f9e890`), chosen by the owner from three options. Each is 3:1 or more on the paper and the surface; they differ in lightness as well as hue; and every pair of them and the chart's accent teal is 20 or more apart, to CIEDE2000, to a reader who sees every colour and, simulated, to one with protanopia, deuteranopia or tritanopia. Tests hold each. Succeeded stays neutral.
  - A badge's word is always in the ink, which reads on its pill, since the gold is 3.4:1 on the paper, a mark's contrast and not a word's. The colour is the border and the shape.
  - Failed, dead-lettered and a budget over are edged and marked in the red; retrying and a budget near in the gold. Retrying has a shape of its own, a hollow diamond, apart from queued's dotted ring and waiting's filled diamond, so no pair of them is told by colour.
  - `--danger` is now an alias of `--status-failed`: one red for a failed run and for a destructive action, the shape and the word telling them apart. The danger colour's tests, including the soft button's words on its hover tint, hold for the new red.
  - Colour-blind mode (ADR-0036) leaves the status colours as they are: they hold their floors to every reader on their own, which the tests hold under each simulated deficiency, and a mode that must change them adds them to its block.
  - Under forced colours the badge's shapes keep their own colours (`forced-color-adjust: none`), so a shape is still told from the next.
- **`Alert`** is a note, a warning or an error in the page: a shape beside its words (info, a triangle for a warning, a circle for an error), the words in the ink, and the edge in the mark's colour. An error is an `alert`; a note and a warning are `status`, so they wait their turn. **`Reading`** is what is being read: a status in words over placeholders (`Skeleton`) in the shape of what is coming, which pulse and do not where motion is reduced, and are hidden from assistive technology. Messages that were paragraphs are alerts, with their words unchanged but for the partial reads', which say less.
- **Lists are one idiom:** `Rows`. The tenant's workspaces and a thread's people with access were a card grid and a bare list. An empty state is smaller, with its one action beneath it.
- **Admin is compact, and the app is not.** The frame sets `data-density="compact"` for admin. Three tokens change under it: `--row-height` (2.75rem to 2.25rem), `--row-pad` (0.5rem to 0.25rem) and `--table-text` (14px to 13px). A table's rows are 36px, and a small action fits; the app's are 44px. Logs' virtualized rows keep their two lines and their height, which a fixed-height list needs, and take the 13px words.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Status colours | **Rose red and gold (chosen, by the owner)** | Meets every floor with the chart's dark teal as it is; near the danger colour it replaces | The gold is 3.4:1 on the paper, so it is a mark and never a word |
| | Brick red and ochre | Earthier | In dark, 10 from the teal to a reader without green |
| | Deep red and amber-orange | Warmer | Likewise |
| Danger | **One red, aliased (chosen)** | A failure and a delete read as one thing | A destructive button and a failed badge share a hue; shape and word differ |
| | Two reds | Each its own | A second red that must clear every floor |
| Density | **Admin only, by a frame attribute (chosen)** | The app stays roomy; one frame attribute | Logs' rows keep their height |
| | Both | One look | The app's lists are read, not scanned |
| Messages | **An `Alert` with a shape (chosen)** | Said by more than colour; the same words | A component where a paragraph was |
| | A toast | Out of the page | Gone before it is read |

## Consequences

- Easier: a surface that floats, a status, a message and a density are tokens or one component; a test holds the status colours to their floors in both schemes and in colour-blind mode.
- Harder: a badge's colour is a mark, so a new status needs a shape as well as a hue.
- To revisit: Logs' two-line rows, if a single-line row is wanted for the 36px the tables have; a toast for what a person did elsewhere.
