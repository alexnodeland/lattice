# ADR-0047: Dashboards on demand, tables by TanStack Table, the panel registry, and one seam for integrations

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** the chart theme of [ADR-0036](0036-the-chart-theme-and-colour-blind-mode.md); the add-ons of [ADR-0044](0044-highlighting-and-math-on-demand.md); and the add-ons seam of [ADR-0043](0043-markdowns-basics.md), as [ADR-0045](0045-integrations-in-admin-and-the-apps-read-of-them.md) feeds it

## Context

[lattice RFC-0005](../../rfcs/0005-forms-dashboards-and-mini-apps.md) has an agent show figures as a dashboard: a snapshot whose panels are plain JSON, `stat`, `bar`, `line`, `donut`, `table`, `text` and `form`, in artifactr.ui's closed schema. portalr draws them in the app. The app has shipped no chart code: only admin imports the kit's charts on Recharts and the chart theme ([ADR-0036](0036-the-chart-theme-and-colour-blind-mode.md)). A table panel holds up to 500 rows, which a plain table can't sort, filter or page.

A brainstorm and a spike measured the candidates under portalr's Content-Security-Policy in Chromium, with real hovers, legend clicks and drags, and by size:

- **Recharts and the chart theme** drew with no violation, took the tokens as `var()` and followed `data-cvd` live.
- **ECharts** broke the policy on every hover with its HTML tooltip, drew `var()` colours as nothing once it derived a colour, and is about 200 kB.
- **TanStack Charts** broke the policy on hover in SVG.
- **Vega** needed `eval` to draw at all.
- **TanStack Table** is headless, about 17 kB, and drew with no violation.

The spike also found a blind spot in the harness. Playwright's `page.evaluate` runs outside the page's `script-src` check, so a library that evaluates strings passed a test that drew from it.

Forms and dashboards are switched per workspace by `ui:forms` and `ui:dashboards`, as Markdown's add-ons are by `markdown:math` and `markdown:mermaid`. [ADR-0045](0045-integrations-in-admin-and-the-apps-read-of-them.md) gave Markdown's add-ons a context of their own, `AddonsProvider`, shaped `{math, mermaid}`; forms and dashboards needed one by key.

## Decision

- **Dashboards are an add-on,** `dashboards` (`ui/src/on-demand/dashboards.tsx`), loaded through [ADR-0044](0044-highlighting-and-math-on-demand.md)'s `useOnDemand` with a dashboard's first chart or table, and kept for the page's life.
  - It holds the kit's charts, drawn `bare` (their legend and plot alone), and a table panel's interactive rows.
  - It loads only while `ui:dashboards` is on in the workspace.
  - If it won't load, as when the network drops its chunk, `useLoaded` says it failed, and a dashboard is drawn as with dashboards off: each chart says it couldn't be loaded and opens its figures, and a table stays plain. A chart is never left drawing for ever. Until the add-on is in, a chart's figure is `aria-busy`, so a dashboard of many charts doesn't announce each.
  - Its ceiling is a total of 150 kB and a largest of 130 kB, gzipped. It measured 126.8 kB, nearly all Recharts.
  - The app's own sizes are 186 / 457 / 136 kB (initial / total / largest), within their ceilings, which are unchanged.
- **Recharts and the chart theme stay.** No ECharts now. A panel that Recharts draws badly, such as a heatmap, a dense scatter or a long series to zoom, brings ECharts as an add-on of its own, about 240 kB, which the owner agrees to first. It would use its SVG renderer, a tooltip built through the CSS object model, and every colour resolved, never `var()`.
- **The panel schema stays closed.** It has no formatter, `renderItem`, URL or anything else that runs. A new type of panel joins one at a time: in artifactr.ui's schema, drift-tested, with its figures and a renderer in the registry.
- **A registry draws the panels.** `PANELS` maps each panel `type` to a renderer, and `DashboardView` takes another (`panels`). A renderer is given the panel, how to show a form, and the chart theme's colours resolved. So a chart or a table can be drawn another way without a change to the panels or the artifact.
- **The figures come from the panel.** Each chart's "Show the figures" is built from the panel's rows and series, or its parts, beside the renderer and never by it, so a renderer can't drop the text equivalent. With dashboards off, a chart isn't drawn, and its figures are open beneath a line that says so. A table panel then shows its rows as they are.
- **`useChartTokens` resolves the chart theme's colours** to what the browser draws, inside the dashboard, so a mode set there alone counts. It reads them after the first render, and again when `data-theme` or `data-cvd` changes on any element, the root or one round the chart, or the system's scheme or forced colours do. It also says whether colour-blind mode and forced colours are on. The kit's charts write `var()` and don't need it, so a dashboard drawn by `PANELS` reads nothing, and its renderers are given `null`; a canvas renderer, or one that derives colours as ECharts does, is given these.
- **A chart and a table are headed alike.** Each is a section under a heading of its panel's label, which names the chart's figure and the table, so a reader moving by headings finds both.
- **A table panel is TanStack Table 9.2.4,** pinned and more than two weeks old. Its rows are sorted, filtered and paged 50 at a time, in the kit's `Table`, named by its panel's heading.
  - **Sorting:** a column's heading is a button in its `th scope="col"`, which says how it is sorted (`aria-sort`, left out where it isn't). One column sorts at a time, with Shift or without. Numbers sort by value, words in British order, and nothing sorts last. Ascending comes first.
  - **Filtering:** one field over every column, named by its panel, such as "Filter Longest open", matching the words a cell reads as.
  - **Pages and the count:** "Previous rows" and "Next rows", grouped as the panel's pages ("Pages of Longest open"), move between pages, and keep the focus on the first and last page, where they can't be pressed. Which rows are shown is said, as a status, once the filter's words settle. A table keeps its page as the dashboard is drawn again, as a stream's events draw it.
  - **Rows:** each row is named by its first cell, a row header, as the kit's tables are.
  - **Native table semantics, not `role="grid"`.** A grid promises arrow keys from cell to cell, and a table of figures to read has nothing to edit. The controls are the kit's: Tab reaches each heading's button and the field, and Enter or Space sorts ([ADR-0037](0037-form-controls-and-row-actions.md)).
  - **No TanStack Virtual.** A panel holds 500 rows at most and shows 50 at a time, and virtual rows would break find-in-page and a screen reader's count of rows.
- **The CSP tests draw from the page's own task.** The harness's page draws what its address names at load: `?markdown=` the Markdown given, whole or streamed, with the integrations named on or off; `?dashboard` the dashboard gallery; and `?eval` an evaluated string. The first test proves the harness sees the page's own `eval` refused, where a test's `evaluate` passes. Markdown's tests draw each gallery and hostile message so. The dashboard's test loads the add-on, moves the pointer across each chart, sorts and filters the table, and opens the figures, with no violation.
- **One seam for integrations.** `IntegrationsContext` is an `isEnabled(key)` over `client`'s `IntegrationKey`, the registry's keys, which the app gives from `useEnabled`. Markdown's add-ons are read from it, `isEnabled("markdown:math")` and `isEnabled("markdown:mermaid")`, so `AddonsProvider` is gone, and the app gives one value.
  - **Defaults, once.** Where no page gives one, as in admin, each integration is its registry default: every one on but `ui:mini-apps` and `markdown:mermaid`. `ui` writes them once, and a test holds them to `schemas/integrations.json`.
  - **The answer is kept.** `useEnabled` answers the same function until a read changes what it read. A form refused as off stays locked until then, and follows the new read after it, so it can be sent again once forms are switched back on.
  - **One wording.** Whatever is off is said of the workspace, as [ADR-0045](0045-integrations-in-admin-and-the-apps-read-of-them.md)'s refusal is: "Not available in this workspace.", and for one of `ui`'s, which, as in "Not available in this workspace: forms are off."

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Charts | **Recharts and the theme, as an add-on (chosen)** | No violation; tokens, `data-cvd` and patterns as they are; tested and pinned already | 127 kB, on demand |
| | ECharts | Panels Recharts can't draw | Violations on hover; derived colours vanish with `var()`; about 200 kB |
| | Vega-Lite as the agent's format | Models write it | `eval` to draw; a language, not data; 274 kB |
| Tables | **TanStack Table, in the kit's markup (chosen)** | Headless; 17 kB; sorting, filtering and pages | A dependency, and v9's API is young |
| | `ItemTable` as it is | Nothing new | No sorting, filtering or pages for 500 rows |
| Table semantics | **A table, with buttons in its headings (chosen)** | What a screen reader expects of figures | No arrow keys from cell to cell |
| | `role="grid"` | Arrow keys | Promises an editing model there isn't |
| Figures | **From the panel (chosen)** | Any renderer keeps its text equivalent | Built beside the chart |
| | From each renderer | One place | A swap could lose them |
| Integrations | **One context by key, Markdown's add-ons read from it (chosen)** | One value from the app; keys typed by the registry; defaults written once | Markdown asks by key, not by add-on |
| | `AddonsProvider` beside a second context | ADR-0045's as it was | Two values from one read, and two sets of defaults to keep the same |

## Consequences

- Easier: a dashboard costs a visit nothing until it is shown, and a renderer can be replaced, for one type at a time, without a change to the panels.
- Easier: the CSP tests catch a library that evaluates strings, which they couldn't, in Markdown and dashboards alike.
- Easier: a new integration `ui` follows is one key, typed by the registry, with its default tested against it.
- Harder: a dashboard's first chart waits for the add-on, busy while it does, and a table is plain until it is in.
- Revisit: ECharts, with the first panel Recharts can't draw well; a table panel past 500 rows, which would need TanStack Virtual and a count said apart from the rows.
