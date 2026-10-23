# ADR-0041: First-party WebAssembly in the UIs' policy

**Status:** Accepted, amended 2026-10-17 (see Amendment: both UIs, one policy), and amended 2026-10-22 by [artifactr ADR-0088](../../artifactr/adr/0088-excalidraws-phase-0-what-the-canvas-costs-and-needs.md)
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** the Content-Security-Policy of [ADR-0011](0011-the-router-and-its-readers.md), and the refusal of `'wasm-unsafe-eval'` on portalr's origin in [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md#alternatives)

> **Amended (2026-10-22) by [artifactr ADR-0088](../../artifactr/adr/0088-excalidraws-phase-0-what-the-canvas-costs-and-needs.md), Excalidraw's phase 0:** Excalidraw's editing compiles no WebAssembly, and its font subsetting needs `'unsafe-eval'`, which this record never allowed. So both UIs' policy drops `'wasm-unsafe-eval'`, and `wasm-allowlist.json` holds both builds to no module. The canvas adds `img-src blob:` alone. `'unsafe-eval'` is never in either UI's policy; subset export is the worker's, on its own isolated page. The guardrails below stay, for a module a UI might need again, which would put the directive back in a reviewed change.

## Context

Both UIs are served with one policy, `policy(site)` in `portalr/fastapi/ui.py`: `default-src 'self'`, `script-src 'self'`, `style-src 'self'`, `img-src 'self' data:`, `font-src 'self'`, `connect-src 'self'` and Supabase, `object-src 'none'`, `frame-ancestors 'none'`. It allows no inline script and no `eval`, and no WebAssembly, since compiling a module needs `'wasm-unsafe-eval'` (or `'unsafe-eval'`). It matters because supabase-js keeps the session in `localStorage` (lattice RFC-0002).

Lattice RFC-0003 refused `'wasm-unsafe-eval'` on portalr's origin. The case it weighed was reaching into WordCraft's unmodified browser build, 40 MB of WebAssembly from a third party, from a page on portalr's origin. It gave that editor an origin of its own instead.

[Lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md) puts Excalidraw's canvas directly in `app`, on portalr's origin, with its session and WebSocket (its O3). `@excalidraw/excalidraw` 0.18.1 holds two WebAssembly modules, harfbuzz and woff2, inlined as base64 in one lazily loaded chunk. It uses them to subset fonts for SVG export. The chunk graph shows nothing in plain editing importing that chunk; RFC-0006's spike checks this in Chromium. The owner decided this on 2026-10-17 (RFC-0006's O4), so it is accepted ahead of the RFC, which is a draft to allow WebAssembly in `app`, for first-party, pinned modules only, with the guardrails below. RFC-0006's spike still establishes whether plain editing needs it, or only export and conversion.

## Decision

- **`app`'s policy gains `'wasm-unsafe-eval'` in `script-src`,** for the whole of `app`. Nothing else in the policy changes. `'unsafe-eval'` stays absent, so `eval`, `new Function` and string timers are still refused; the directive allows compiling WebAssembly and nothing more.
- **admin's policy doesn't change.** `ui_router` sets each UI's policy from its name, instead of one for both. admin bundles no WebAssembly and doesn't need it.
- **Guardrails:**
  - **Modules ship only in our build.** Every WebAssembly module `app` may compile comes from a package in `bun.lock`, built by Vite into the wheel's `static/app/`. Nothing is fetched at run time from anywhere else: `connect-src` stays `'self'` and Supabase, and Excalidraw's font and asset path points at our own files, never at esm.sh.
  - **A test lists every module.** `web/wasm-allowlist.json` names each WebAssembly module in each UI's build: the package, the built file that holds it, and the SHA-256 of the module's bytes. The test finds modules both as `.wasm` files and inlined in JavaScript, by the `\0asm` magic and its base64 form (`AGFzbQ`), since 0.18.1 inlines its modules. It fails on a module not listed, a listed one missing, or a digest that changed. It runs in `portalr:check`, beside the size budgets. A module is added or its digest changed only in a reviewed change that says why, as a budget is raised ([ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md)).
  - **No third-party-hosted or agent-authored WebAssembly.** Nothing a model writes is compiled on portalr's origin; lattice RFC-0005's non-goal, no code from a model on portalr's origin, stands. Markdown is rendered without raw HTML ([ADR-0015](0015-the-chat-components-and-streamdown.md)), and a byte array in an artifact's data is never handed to `WebAssembly`.
  - **Mini apps get none.** RFC-0005's mini apps stay on their cookie-less origin, `apps.<host>`, whose proxy is served with `default-src 'none'` and no `'wasm-unsafe-eval'`. The inner frame inherits that policy. RFC-0005's phase 2 tests gain one case: `WebAssembly.compile` fails inside a mini app.
  - **The policy is tested exactly.** `tests/fastapi/test_ui.py` holds each UI's policy directive by directive, on `index.html` and on a hashed worker script under `assets/`, since a worker takes its policy from its own response. A widening is a visible change.
- **RFC-0003's own case is still refused.** Its other reasons stand: WordCraft's build is a third party's, unmodified, 40 MB, with internals that change every release. Its editor keeps an origin of its own. This record admits WebAssembly that lattice pins and lists, not any WebAssembly on portalr's origin.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Where | **`app`, app-wide, with guardrails (chosen)** | One origin, one session, one WebSocket for the canvas, the owner's choice | Every page of `app` may compile WebAssembly, though only one chunk holds any |
| | A third UI, `canvas`, with its own policy | The directive only where the canvas is | A second entry, shell and session handover; the owner chose `app` |
| | An origin of its own, as RFC-0003's editor | portalr's origin keeps today's policy | A token handed over `postMessage`, a second WebSocket, and a canvas cut off from the app's components |
| How | **Guardrails: our build, an allow-list by digest, no egress (chosen)** | A new module can't arrive unnoticed | One more list to keep up |
| | The directive alone | Nothing to keep | Any dependency could start compiling WebAssembly unseen |
| | No WebAssembly: SVG export in the worker only | Today's policy | Turns the canvas's own export off; and the spike, not this record, says whether editing needs it |

## Consequences

- Easier: the canvas runs in `app` as released, with SVG export in the browser, and shares the app's session, WebSocket, components and tokens.
- Harder: `app`'s policy is looser than it was. A cross-site scripting flaw in `app` could now also compile WebAssembly; it could already run script, so the added reach is speed and obscurity, not access. Every bump of a package that holds WebAssembly changes the allow-list.
- Revisit: if RFC-0006's spike shows that no feature `app` ships compiles WebAssembly, for example because export moves to the worker, this record is superseded and the directive is dropped. Also revisit if Excalidraw starts to load modules from elsewhere.
- admin is unchanged.

## Action items

1. [ ] `ui_router`: a policy per UI, with `'wasm-unsafe-eval'` for `app` only, and `test_ui.py` holding both exactly.
2. [ ] `web/wasm-allowlist.json` and its test in `portalr:check`.
3. [ ] RFC-0005's mini-app tests: `WebAssembly.compile` fails in the frame.
4. [ ] RFC-0006's spike records whether editing compiles WebAssembly, and this record is revisited if nothing does.

## Amendment, 2026-10-17: both UIs, one policy

The owner decided that admin allows first-party WebAssembly too, under the same guardrails. It is done before either half of the split was built, so `ui_router` keeps the one policy it had.

- **Both UIs' policy gains `'wasm-unsafe-eval'` in `script-src`.** Nothing else in it changes, and `'unsafe-eval'` stays absent. "admin's policy doesn't change" and "admin is unchanged" above are superseded.
- **One policy, not one per UI.** `policy(site)` stays the one both UIs are served with, and the split this record planned isn't built. With both UIs allowing the same thing, a policy per name would be a branch with nothing to choose between, and a second policy to test. `ui/csp/policy.txt`, which a portalr test holds to `policy()`, is then the policy both UIs share, not one of two. Action item 1 is revised to this.
- **The guardrails cover both UIs.** Modules ship only in our build, and `connect-src` stays `'self'` and Supabase. Nothing third-party-hosted or agent-authored is compiled, and RFC-0005's mini apps stay on their own origin with none.
- **The allow-list is kept by digest.** `web/wasm-allowlist.json` lists, for each of `app` and `admin`, each module's package and the SHA-256 of its bytes. `scripts/check_wasm.py`, the `portalr:wasm` task that `portalr:check` runs, finds modules in each built UI both as `.wasm` files and as base64 inlined in any other file (`AGFzbQ`, the encoding of `\0asm`). It fails on a module not listed, a listed one the build doesn't hold, and raw magic in a file written as text, such as a script, which it can't delimit; in a font or an image such bytes are chance, and aren't looked for. Entries don't name the built file, since Vite's names change with every build; the check reports the file that holds each module. Both lists are empty today: neither build holds a module.
- **The policy is tested exactly.** `tests/fastapi/test_ui.py` holds the shared policy directive by directive, on each UI's `index.html` and on a hashed script under `assets/`.
- **Markdown still needs none.** The policy can no longer refuse a module in ui's CSP harness ([ADR-0043](0043-markdowns-basics.md)), so the harness's page reports each call that compiles or instantiates WebAssembly, and every case still expects nothing reported: `Markdown` and its add-ons compile no WebAssembly ([ADR-0044](0044-highlighting-and-math-on-demand.md)). A case of its own compiles the smallest module, to show the policy allows it and the harness sees it.
- **Revisit, for either UI.** The directive is dropped if RFC-0006's spike shows that no feature of either UI compiles WebAssembly.
- **Harder, now for admin too.** A cross-site scripting flaw in admin, the operator's UI, could also compile WebAssembly. As for `app`, it could already run script, so the added reach is speed and obscurity, not access.

Action items, as amended:

1. [x] `ui_router`: one policy for both UIs, with `'wasm-unsafe-eval'`, and `test_ui.py` holding it exactly on both.
2. [x] `web/wasm-allowlist.json` and its check in `portalr:check`, for both UIs.
3. [ ] Unchanged: RFC-0005's mini-app tests: `WebAssembly.compile` fails in the frame.
4. [ ] Unchanged: RFC-0006's spike records whether editing compiles WebAssembly, and this record is revisited if nothing does.
