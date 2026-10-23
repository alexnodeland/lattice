# ADR-0088: Excalidraw's phase 0, what the canvas costs and needs

**Status:** Proposed
**Date:** 2026-10-22
**Deciders:** Alex Nodeland
**Records:** [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 0, the spike, and the owner's decisions on it
**Amends:** [portalr ADR-0041](../../portalr/adr/0041-first-party-webassembly-in-the-apps-policy.md)

## Context

RFC-0006's phase 0 was a throwaway spike. Its exit criteria:

- whether editing needs `'wasm-unsafe-eval'`;
- every policy directive Chromium needs;
- the canvas's sizes and its budget ceilings;
- export and conversion on Chromium and on jsdom with resvg;
- where artifactr slows as a scene grows;
- the revisions a person makes an hour.

It measured Excalidraw 0.18.1 in a minimal Vite 8 app with portalr's React, served under portalr's policy in a real Chromium 156. Timings are indicative, from one Apple-silicon laptop. Before it, U3 to U6 were signed off and the data layer was built: the `artifactr[excalidraw]` extra, off by default ([ADR-0086](0086-diagrams-data-an-element-scoped-patch-and-its-checks.md)). An upgrade of Excalidraw re-runs its method, as this record describes it: the spike's scripts were throwaway and aren't in the repository.

## Decision

The policy change is implemented by #629, and the element and render checks by #630. The budgets, the `check_size.py` change, the esm.sh build test, the worker and the fonts come with the canvas, in phases 2b and 3.

### The policy (amends portalr ADR-0041)

| Step | Violations under portalr's policy | WebAssembly compiled |
|---|---|---|
| Open the canvas; draw shapes, arrows, Latin and CJK text, freedraw; dark theme; PNG export; an image from a data URL | none | no |
| An image pasted as a file | `img-src blob:` | only pica's, and only where `'wasm-unsafe-eval'` and `blob:` are both allowed |
| `exportToSvg` with fonts embedded | `'unsafe-eval'` (font subsetting); `style-src-attr` from `canvas.js`, which changed nothing | no |

- **Editing never compiles WebAssembly,** so both UIs' policy drops `'wasm-unsafe-eval'`. Nothing either UI ships compiles a module, so it is dropped now, in its own change. `web/wasm-allowlist.json` stays empty, and `scripts/check_wasm.py` holds both builds to no module. Without the directive, pica, the image resizer, falls back to JavaScript. The directive would buy pica's speed and nothing else seen; that speed wasn't measured (unverified).
- **`img-src blob:` is the one directive the canvas adds,** when it lands (phase 3). Without it a pasted image isn't resized, and its stored data URL is about four times larger.
- **`'unsafe-eval'` is never in the app's policy.** Font subsetting needs it, so it fails under both policies: the browser's export then embeds whole fonts (an SVG of 299 kB against 15 kB). Subset export is the worker's job. `'unsafe-eval'` is allowed only on the worker's isolated page, which has no egress and runs no model-authored code. The subsetting chunk (741 kB gzip) is stubbed out of portalr's build.
- **No esm.sh.** Every `@font-face` lists esm.sh as a second source: opening the canvas tried 230 blocked requests even with `EXCALIDRAW_ASSET_PATH` set. The fallback is removed at build time, and a build test, to be built, fails if the build names esm.sh.
- **Other directives:**
  - `style-src 'self'` is enough;
  - `img-src data:` stays;
  - `connect-src` stays `'self'`;
  - `worker-src` isn't needed by name: pica's `data:` and `blob:` workers caused no violation, though that is unverified.

### The budgets

| What | gzip bytes |
|---|---|
| `canvas.js` | 340,104 |
| `canvas.css` | 22,153 |
| Loaded on open (the English locale, file open and save, `roundRect`) | 2,914 |
| **Editing, in all** | **365,171** |
| Image insert (pica, image-blob-reduce) | 28,362 |
| Font subsetting | 740,691 |
| 51 other locales | 394,349 |

- **The canvas is an add-on with a budget of its own.** It would break `app.largest` (160,000) alone, but `app.initial` (202,000) doesn't move, since it is lazy.
  - `canvas`: 402,000 total, 375,000 largest;
  - `canvas-images`: 32,000 total, 18,000 largest;
  - no export budget.
- **`check_size.py` is to learn the canvas's root,** since today it treats only modules under `ui/src/on-demand/` as add-ons, and counts everything reachable.
- **The other locales and the subsetting chunk are kept out of the build,** not just out of the count, with a build test.

### The limits

1 MiB of data and 2,000 elements, tombstones included, enforced by the type on every surface. The cost table is in [ADR-0086](0086-diagrams-data-an-element-scoped-patch-and-its-checks.md). The RFC's 5,000 would be about 2.9 MB and 200 to 400 ms a commit.

### A full diagram can't shrink, until the sweep

With a hard cap of 2,000 elements, tombstones included, and no `remove` but the sweep's, a diagram at the cap can never shrink: deleting marks an element, and the mark still counts. So U3, the tombstone sweep, is a named follow-up PR, after this record, before the canvas ships.

### Cadence and retention

| Rule | Changes | Commits | An hour |
|---|---|---|---|
| U4 as written: pointer-up, 1 s idle, at most 1 a second | 891 | 55 | 1,650 |
| Pointer-up, 2 s idle, at most 1 every 5 s | 1,020 | 25 | 750 |

This was 120 s of one scripted busy person on the real canvas. Every revision stores the whole scene: under U4 as written, about 58 MB a person-hour at a 30 KB scene, and about 2 GB at the 1 MiB cap.

- **The canvas commits on pointer-up and after two seconds idle, at most once every five seconds per person and diagram.** This replaces U4's one second.
- **A retention rule for diagram revisions is a follow-up,** in an artifactr ADR of its own. An example: revisions older than a day thinned to one an actor every ten minutes, keeping proposals' bases.

### The worker

Headless Chromium, as U6 has it. The SVGs jsdom wrote were byte-identical to Chromium's for the flow, text, CJK, freedraw-with-image and 1,334-element scenes; the 6,667- and 26,667-element grids weren't compared. resvg's PNGs aren't: two of seven font families fell back, and an embedded image was drawn wrong. jsdom also needs a native canvas and more memory.

| Cost | Chromium | jsdom and resvg |
|---|---|---|
| Resident memory | 375 MB ready; 591 MB at 1,334 elements | 370 MB at 1,334; 2.8 GB at 26,667 |
| 1,334 elements, warm | about 150 ms | 0.6 to 1.25 s |
| 26,667 elements, SVG / PNG | 406 / 2,717 ms | 1,794 / 11,385 ms |

- One warm browser, one job at a time, 1 GB, a 10 s deadline. Within the 2,000-element limit, a job fits well inside it. One job at a time is for every tenant together: no tenant has a bound of its own on the worker's time yet ([ADR-0090](0090-diagrams-drawn-by-the-agent-through-a-converter.md)).
- Its isolated page alone allows `'unsafe-eval'`, for subset export.
- It has a CJK face, without which it draws tofu.

### Fonts

- **Latin faces are self-hosted.** A build script copies them and sets `EXCALIDRAW_ASSET_PATH`: Vite emits only the Assistant faces, and the hand-drawn ones load at run time.
- **Xiaolai, the CJK face (12 MB in 209 files), ships only in the worker's image.** Browsers fall back to a system CJK face, which is readable but not hand-drawn; the element's stored width was the same.
- **Licences come from pinned upstream commits.** The package ships no licence file for itself or its fonts. Virgil, Assistant, Cascadia and Comic Shanns were verified from their metadata. Nunito and Lilita One carry only the OFL's URL: their OFL text is to be verified before they ship. Excalifont, Liberation and Xiaolai weren't verified, and must be before they ship.
  - All 81 bundled packages are on portalr's notices allow-list.
  - `@excalidraw/excalidraw`, 23 `@radix-ui` packages and `react-remove-scroll-bar` need `exceptions` entries for their missing licence files.

## Consequences

- Easier: both UIs' policy is tighter than before, and the canvas adds only `img-src blob:`.
- Harder: an export from the browser embeds whole fonts; a small export is the worker's.
- Harder: revision storage grows with the scene until the retention rule lands.
- Harder: upgrading Excalidraw means re-running the spike's method. Its `main` already reworks the API (`onExcalidrawAPI`, no `restore()`, new arrow bindings).
- **Carried, unverified:**
  - presence over PostgreSQL `LISTEN`/`NOTIFY` for 10 peers at 20 Hz;
  - the conflict rate with three people and an agent;
  - Mermaid conversion in the worker;
  - focus and screen readers on the canvas;
  - `UIOptions` and palette presets;
  - `customData` surviving `restoreElements`;
  - why the subset worker fails even with `'unsafe-eval'`;
  - how to remove the esm.sh fallback and the locales without a patch;
  - jsdom's dev server rebuilding the subset worker;
  - drift between people with Xiaolai and without it;
  - PostgreSQL's write costs;
  - the licences of the WebAssembly modules (harfbuzz, woff2 and pica's).
