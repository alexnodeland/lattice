# ADR-0072: A diagram's card, and its canvas to look at

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

Records portalr's half of [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 3, its first part: the renderer for `excalidraw_diagram` and the canvas that shows a diagram whole. It builds on [artifactr ADR-0088](../../artifactr/adr/0088-excalidraws-phase-0-what-the-canvas-costs-and-needs.md)'s measurements, on the description the agent reads ([artifactr ADR-0090](../../artifactr/adr/0090-diagrams-drawn-by-the-agent-through-a-converter.md)), and on the add-ons [ADR-0044](0044-highlighting-and-math-on-demand.md) set up.

## Context

- **The agent draws diagrams** (artifactr ADR-0090), and the app showed them as JSON.
- **Excalidraw is large.** Its canvas, with the code it reaches, is hundreds of kilobytes gzipped. The app's first load had about 600 bytes of room below its ceiling, and its total about 12 kB.
- **Excalidraw's build reaches for more than the canvas needs.** It has font subsetting (741 kB, with WebAssembly), Mermaid's converter, image resizing, 55 locales, esm.sh as a fallback for its faces, and Xiaolai, a CJK face whose licence is unconfirmed (lattice#679).
- **Editing needs more than this phase has.** An edit needs three things that don't exist yet:
  - a TypeScript port of the element-scoped patch (artifactr ADR-0086);
  - a route to upload a pasted image to;
  - the commit cadence and reconcile that collaboration brings.

## Decision

### The card

- **`excalidraw_diagram` has a renderer of the app's own** (`app/src/diagram.tsx`). It draws a card: the diagram's name, how many live elements it holds, its text version in a disclosure, and **Open canvas**.
- **The text version is the description the agent reads.** `app/src/diagram-text.ts` ports artifactr's `describe` to TypeScript. It is the diagram's text alternative: Open canvas and the canvas's dialog are described by it (`aria-describedby`). It is also the text a revision's changes are compared by, line by line.
- **The port is held to the Python by one fixture.** `packages/artifactr/schemas/excalidraw_descriptions.json` is written by artifactr's tests (`tests/excalidraw/descriptions.py`) and checked by both sides. It covers:
  - control, bidirectional and tag characters, and the joiners that stay;
  - Python's white space;
  - CJK;
  - the 4,000-character cut;
  - numbers as Python's `g` writes them, ties to even, which the port does exactly, from a double's binary value;
  - what isn't a string or a number. Both sides take only a string as words and only a number, not a boolean, as a place, so what JSON holds reads alike in both.
  - Both read a diagram's elements in JavaScript's order of an object's keys: keys that are array indexes first, as numbers, then the rest as written. artifactr's `describe` orders them so, since JavaScript can't read them any other way.
- **A diagram's words are data.** Anyone in the workspace may write them, so they are only ever React text, never markup.
- **The card is drawn with what the routes that show artifacts already load:** the kit's button and disclosure, and its loader. So neither the first load nor those routes carry more for it.

### The canvas

- **A chunk of its own, the `canvas` add-on** (`app/src/on-demand/canvas.tsx`). It holds Excalidraw 0.18.1, the version `versions.env` names and `check_diagrams` holds the app to. It is loaded only when someone presses **Open canvas**: nothing preloads it, and no route loads it.
- **It opens in a dialog that fills the window** (ui's `WholeDialog`):
  - Tab is kept in it at once, as the kit's dialogs keep it (`keepTabWithin`, ADR-0068);
  - the page behind is hidden from assistive technology;
  - Escape, or **Close canvas**, closes it, and the focus goes back to Open canvas.
  - Opened from a chat card's full view, it closes alone: the full view stays.
- **To look at, in this phase.** The canvas is in view mode: it pans and zooms, with no tools.
  - **A diagram's elements are anyone's to write, so the canvas takes only what it draws.**
    - No link, so a click opens nothing.
    - No embedded page (`embeddable`, `iframe`), with `validateEmbeddable` off, so no frame is made.
    - No image.
    - No number that isn't finite, and no points that aren't pairs of numbers.
  - Each element is restored by Excalidraw, together so labels and bindings hold, and one at a time where that throws, passing over the ones it can't mend.
  - A diagram the canvas still can't draw falls back, inside the dialog, to why, and its text version.
  - **View mode is kept at the canvas's edge, not only by hiding Excalidraw's UI.** Only Tab, Escape, the arrows and zoom reach it: `?` for help, ⌘/ or ⌘K for the palette, ⌘S and ⌘O never do, nor the browser's own save and open. A drop, a paste and the context menu are refused there too. Its main menu and help aren't shown. The canvas writes nothing to localStorage or IndexedDB.
  - Images aren't loaded yet: an image element shows Excalidraw's placeholder.
  - **Editing, pasted images and their checks come in phase 3b,** before collaboration (PR 4): the TypeScript patch builder, an upload route for a diagram's images with checks of size and type in the app and in the server, no SVG images, and `img-src blob:` in the policy, then and not before.
- **Its theme is the page's,** and its primary colours are the brand kit's accent. In dark mode Excalidraw draws the scene through its own inverting filter, so the elements' colours there are Excalidraw's, not the kit's.

### The build (`app/excalidraw.ts`)

- **What the canvas never runs is built as a module that refuses:**
  - font subsetting, whose export embeds whole faces instead (artifactr ADR-0088);
  - Mermaid's converter, which runs only in the diagrams worker (stackr ADR-0049);
  - pica and image-blob-reduce, which resize an image put on the canvas.
- **The locales but English are built as nothing.** A build check refuses Mermaid, pica and image-blob-reduce in any chunk.
- **No face is fetched from a CDN.**
  - The faces but Xiaolai are copied beside the app, at `excalidraw/fonts/`, which `EXCALIDRAW_ASSET_PATH` names.
  - The esm.sh fallback Excalidraw names is rewritten to that copy, and the build fails if any file it writes names esm.sh.
  - **Xiaolai isn't registered,** so nothing asks for it: browsers draw CJK with a face of their own.
- **The canvas's modules are its own.**
  - A module both the canvas and the rest of the app import would be split into a chunk of its own, which the first load fetches and every route's chunk names. Excalidraw's radix brings `@floating-ui` and `tslib`, which the kit uses too, and that put 1.3 kB on the first load.
  - The build marks every module the canvas reaches as the canvas's own, so it keeps its own copy. React is the one module shared, as there must be one React.
- **esbuild's stand-in for `require`,** which Excalidraw's build keeps and a browser never calls, is kept as what it does in a browser: throw. Otherwise the bundler puts its own helper in the runtime every chunk shares. The rewrite matches Excalidraw's production build and its development build, which the vitest projects load; if either stops matching, the build fails, saying so.
- **Every locale but English** is matched by its file, whatever its code (`kaa`, `kab-KAB`, `ckb-IQ`), and a build check fails if any is built.

### The policy

- **Unchanged.** The view-only canvas draws under the policy both UIs share, with no violation and no WebAssembly.
  - It needs no `img-src blob:`: that comes with pasted images, in phase 3b.
  - It needs no `'wasm-unsafe-eval'` and no `'unsafe-eval'`.

### Sizes

Gzip, against stackr ADR-0049's commit:

| | Before | After | Ceiling |
|---|---|---|---|
| app initial | 202,363 | 202,357 | 203,000 |
| app total | 462,737 | 465,073 | 475,000 |
| `canvas` add-on, total / largest | | 339,571 / 157,700 | 350,000 / 165,000 |

ADR-0088 proposed a `canvas` of 402,000 / 375,000 and a `canvas-images` add-on of 32,000 / 18,000. The images' code isn't built here, so `canvas-images` has nothing to measure until phase 3b, and `canvas` is tighter than proposed.

### Tests

- **The CSP harness opens the card and its canvas under the shared policy.** It checks that the canvas:
  - loads only when opened, and has no violation;
  - compiles no WebAssembly;
  - asks for nothing on any origin but the page's own, its faces included;
  - is reached and left by the keyboard, with the focus given back to Open canvas.
- **A thread's test** opens the canvas from a chat card's full view, and checks that Tab stays in the canvas and that Escape closes it alone.
- **A scenario of the app's** (`diagrams.feature`), against portalr's test application and its router's own headers:
  - the assistant draws from Mermaid, and the diagram is proposed and accepted;
  - its card and text version show;
  - its canvas opens with no violation and no request off the portal's origin;
  - Escape closes it, and Open canvas has the focus.
- **The notices** carry Excalidraw's packages. Exceptions name the ones that ship no licence file (Excalidraw, 23 radix packages, react-remove-scroll-bar), and pako, whose zlib port is under the Zlib licence.

## Options considered

### For the first load

| | The canvas's modules its own (chosen) | Shared modules left to the bundler | A manual chunk for the shared modules |
|---|---|---|---|
| First load | Flat | +1,324 bytes, over its ceiling | A chunk the first load still fetches |
| The canvas | A few kB of copies | Smaller | Smaller |
| To keep | One rule: React is shared | Nothing | A list of modules to keep in step |

### For the text alternative

- **The Python's description, ported and held to it by a fixture (chosen):** one description, for the agent and for people, which can't drift.
- **A description of the canvas's own, from Excalidraw:** a second wording, which nothing would hold to the agent's.

### For editing

- **View-only now, editing in phase 3b (chosen):** the canvas, its build and its tests reviewed alone.
- **Editing here:** a patch builder, an upload route and the policy's `blob:` in one change, ahead of the server side they need.

## Consequences

- Easier: a diagram reads as itself, in words and on its canvas, at no cost to the first load. The canvas loads only for whoever opens it.
- Harder:
  - `bun.lock` now holds Excalidraw's whole tree, which installs and osv read: mermaid-to-excalidraw with mermaid, d3 and cytoscape, sass, cross-env and random-username, though none of it is bundled. The security pins of nanoid and lodash-es at the root's `overrides` are stackr ADR-0049's.
  - The app carries about 480 kB of faces beside it, not counted in its budgets, which count no typeface.
  - The canvas carries its own copies of what the kit shares.
  - Upgrading Excalidraw means checking each rewrite still matches: the face fallback, Xiaolai's registration and esbuild's stand-in. The build fails, saying which, if one doesn't.
  - Numeric element ids lose their order in a JSON object, as JavaScript reads one, so the port lists them first. The fixture has none, and the diagrams worker and the canvas make none.
- To revisit:
  - Xiaolai once its licence is confirmed (lattice#679);
  - Excalifont's and Liberation's licences, which ship meanwhile, marked unverified (lattice#679). Their own metadata gives none: Excalifont's says "All rights reserved", and Liberation Sans' refers to Ascender's licence agreement, not the SIL Open Font License that Liberation 2 is under;
  - Cascadia Code's, whose metadata names the SIL Open Font License's URL beside Microsoft's text for a font supplied with a product. `web/ui/licenses/excalidraw-faces.txt` carries each face's own notice, as its metadata holds it.

## Action items

1. [x] The renderer, the TypeScript description and its shared fixture.
2. [x] The canvas add-on, its build and its budget.
3. [x] The CSP harness's canvas page, the thread's test and the scenario.
4. [ ] Phase 3b:
   - the TypeScript patch builder;
   - an upload route for a diagram's images, with the app's and the server's checks of size and type, and no SVG images;
   - `img-src blob:`;
   - editing on the canvas.
5. [ ] Phase 3's collaboration (PR 4): presence, the cadence and reconcile.
