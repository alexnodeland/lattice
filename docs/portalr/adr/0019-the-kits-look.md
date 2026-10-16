# ADR-0019: The kit's look: a side rail, labelled icons, raised surfaces and quiet statuses

**Status:** Accepted, amended by [ADR-0036](0036-the-chart-theme-and-colour-blind-mode.md) (the chart series' tokens) [ADR-0037](0037-form-controls-and-row-actions.md) (controls and buttons) and [ADR-0039](0039-elevation-status-colour-states-and-density.md) (status colours, elevation and density)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

The app worked but was bare. It had no frame or navigation chrome, and its workspace title was unstyled. Its lists were plain stacks, there were buttons everywhere, and its hierarchy was weak. `ui` had tokens and a few primitives ([ADR-0009](0009-ui-tested-in-chromium-in-both-schemes-under-bun.md)), but nothing to build a screen's frame from. Three directions were drawn and rendered in both schemes, wide and on a phone, before this design pass:

- **A, Margin:** a side rail.
- **B, Masthead:** the docs site's header and tabs.
- **C, Workbench:** an icon rail, a list pane and dense tables.

The pass followed the principles lattice already shows:

| Principle | Source |
|---|---|
| **Tokens only.** Components use the brand-neutral roles, and anything derived comes from `--accent`, so a `[data-brand]` screen re-skins it | [lattice ADR-0014](../../adr/0014-portalrs-and-grantrs-marks.md); [ADR-0009](0009-ui-tested-in-chromium-in-both-schemes-under-bun.md) |
| **Both schemes from one `light-dark()` pair**, every test run in each | [ADR-0009](0009-ui-tested-in-chromium-in-both-schemes-under-bun.md) |
| **Contrast asserted, not judged by eye:** text 4.5:1 or more, the foreground 7:1, the focus ring 3:1 against every surface | `tokens.test.ts`; lattice's [brand page](../../assets/brand/README.md) |
| **The plates are never text.** Violet is the working colour, for actions and links. Headings stay in the text colour | [lattice ADR-0014](../../adr/0014-portalrs-and-grantrs-marks.md); the brand page's palette rule |
| **Never colour alone.** Links are underlined, and a diff says "added" and "removed" | `docs/assets/stylesheets/lattice.css`; [ADR-0017](0017-the-artifacts-and-proposals-areas.md) |
| **lattice's type:** Schibsted Grotesk, and Fragment Mono for code | the brand page's Type section |
| **The marks are the only decoration**, and `app` and `admin` are told apart by their mark's open side | the brand page; [lattice ADR-0014](../../adr/0014-portalrs-and-grantrs-marks.md) |
| **Roles and accessible names**, which the tests find things by | [ADR-0015](0015-the-chat-components-and-streamdown.md) |
| **Plain English in the components** | [ADR-0014](0014-the-apps-shell.md) |
| **Restraint:** Base UI in shadcn's shape, and only the actions grantr allows | lattice [RFC-0002](../../rfcs/0002-portalr-the-portal.md#ui) |
| **Reduced motion is respected** | `switch.tsx` |
| **The UIs' CSP:** `font-src 'self'` and `style-src 'self'` | `src/portalr/fastapi/ui.py` |

The pass also found five faults in `ui` as it was:

- Text fields were bordered in `--line`, at 1.43:1, under the 3:1 WCAG asks of a control's boundary.
- Schibsted Grotesk was named but never loaded, and the CSP would have refused it from Google Fonts.
- Hover and disabled were opacity, which lowered contrast.
- A paused run had no one wording: the chat said "Waiting for you", and the Runs area, then in review, its own.
- In dark, `--surface` was lattice's cyan-black, `#0d1920`, which is darker than the paper and of another hue.

## Decision

- **The frame is a side rail (direction A).** `AppShell` holds the lockup, the `Switcher`, a `SideNav` and the `AccountMenu` in a rail on the surface from 1024 pixels. The rail stays put as the page scrolls. Narrower, a bar holds the mark, the switcher and the account, and Menu opens the navigation in a drawer: a Base UI Dialog that keeps the focus, closes on Escape, on Close or on following a link, and gives the focus back to Menu. `ui` (`app | admin`) chooses the mark, so `admin` is told apart by the side its mark opens to. A skip link comes first. The header renders the switcher, the navigation and the account once, and CSS moves them between rail and bar; the drawer is modal, and widening past 1024 pixels closes it. Cards hold what asks something of the reader, and `Table` is for rows; the list pattern, lined rows, comes with the areas' restyle.
- **Icons are Lucide's** (`lucide-react`, pinned at 1.55.0, ISC), the set the docs site's scheme toggle already uses. `Icon` hides each one from assistive technology, and every icon sits beside the word that names its control: never icon-only.
- **The dark surface is raised and violet, `#1f1829`,** lighter than the paper. A test holds it lighter in both schemes.
- **A status is neutral: a shape and a word** (`StatusBadge`). Only waiting for you takes the working colour, and the inks stay in the marks. Each shape stays its own when motion is reduced: working is an open ring, still, where queued is dotted. A paused run says "Waiting for you" wherever it is shown, through `RunStatus`.
- **Four tokens join the roles,** each asserted in both schemes and listed below. `--wash` and `--accent-hover` are declared on `:root` and again on `[data-brand]`, since a custom property is resolved where it is declared.
- **No opacity for state.** A disabled control keeps its words in the quiet text, with a line border and no fill. Hover is `--wash` or `--accent-hover`. Whatever is chosen or pressed has one look: the wash, its words in the working colour, edged in it. That is a pressed toggle, the chosen segment of a `SegmentedFilter` (a radio group, its counts said after their words), and the current area in the navigation. The item a menu's keyboard is on is washed, in the working colour, and ringed in `--focus` inside its edge, since the wash alone is 1.28:1 on the surface in light and 1.15:1 in dark. A `Table`'s horizontal scroll is a region named by its caption that the keyboard can reach. Colour transitions stop under reduced motion. The tests run with motion reduced, so a colour is read where it settles, and a browser command, `reduceMotion`, lifts it to see what it stops.
- **The typefaces are self-hosted** under `ui/src/fonts/`. Schibsted Grotesk is variable, upright and italic; Fragment Mono is 400. Each is cut to Latin and Latin Extended, from Fontsource's 5.3.0 files, with `font-display: swap`. Vite emits them beside each UI's assets, so the CSP's `font-src 'self'` serves them. Both are under the SIL Open Font License 1.1. Their licences sit beside them and in the wheel's `licenses/`, and portalr's licence expression is `MIT AND OFL-1.1`. The expression covers portalr's own code and the typefaces it redistributes as files; the JavaScript libraries the UIs bundle, Lucide (ISC) and React (MIT) among them, are under their own permissive licences, which it doesn't restate. `ui-in-wheel` fails unless each UI carries its typefaces and the wheel carries both licences. `admin` now imports `ui`'s styles too.
- **Screenshots pin how the parts sit together.** `gallery.screenshot.test.tsx` renders the frame, with every new component in it, wide and narrow, in each scheme, with motion reduced and the faces loaded. Its baselines are Linux's and are made in CI: the file runs only where `CI` is set. On a mismatch or a missing baseline, CI's Check job uploads `ui-screenshots`, which holds what the run took. Updating a look means reviewing those files and committing them under `src/__screenshots__/`, without their `-reference` or `-actual` suffix. Computed styles still pin each component's colours and states.

### The new tokens

| Token | Light, dark | For | Contrast, light / dark |
|---|---|---|---|
| `--edge` | `#857a97`, `#7d7091` | A control's boundary: fields, secondary buttons, the switcher, filters | 3.69 on paper, 4.02 on surface, 3.14 on wash / 4.05, 3.77, 3.27 |
| `--wash` | `color-mix(in srgb, var(--accent) 10%, var(--paper))` | Hover, the current place, what is pressed or added | fg 13.09 / 13.03; muted 5.51 / 7.41; accent 6.46 / 10.10; focus 6.46 / 7.51 |
| `--accent-hover` | `color-mix(in srgb, var(--accent) 88%, var(--on-accent))` | The working colour, hovered | on-accent 6.20 / 9.88 |
| `--scrim` | `rgb(28 29 38 / 45%)`, `rgb(0 0 0 / 60%)` | Behind the drawer | Not text |

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Frame | **A, side rail (chosen)** | Holds `admin`'s seven areas; the switcher and the lockup always in reach | Phones open the navigation with a tap |
| | B, header and tabs | Closest to the docs site | Tabs can't hold `admin`'s areas; the switcher scrolls away; "Rules" falls off a phone |
| | C, icon rail and panes | Densest | Icons as the only labels; tiny type; three panes fix every area's layout |
| Icons | **Lucide, labelled (chosen)** | lattice's set already; faster scanning | More to draw than words alone |
| | Words only | The least decoration | The rail reads slower |
| Dark surface | **Re-tint to `#1f1829` (chosen)** | Raised cards in portalr's own hue | One more number that differs from the site |
| | Keep `#0d1920` | lattice's site background | Sunken, cyan cards on violet paper |
| Status | **Neutral, the accent for waiting for you (chosen)** | One colour means "act" | Failed reads by its square and word, not red |
| | Magenta marks for "needs you" | Louder | An ink as signal; cyan and yellow fail 3:1 in light, so it can't extend |
| Screenshots | **Vitest's `toMatchScreenshot`, in CI (chosen)** | No new tool; baselines from the runner CI uses | Not run locally; an update goes through CI's artifact |
| | Run them locally too, in Playwright's container | Run anywhere | A Node-based image beside Bun, and baselines that drift from CI's runner |

## Consequences

- Easier: every area in the follow-up builds on one frame and one set of components, and `admin`'s frame is the same component with its own mark.
- Easier: a token, a contrast, a focus ring or a state that breaks fails a test in the scheme it breaks in, and a change in how parts sit together fails a screenshot.
- Harder: a change to the look needs its screenshots taken by CI and committed.
- Harder: text outside Latin and Latin Extended falls back to the system's faces.
- To revisit: the areas themselves, restyled onto the frame after the Rules area lands, with their BDD selectors moved only where a role or a name changes.
