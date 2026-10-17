# ADR-0041: First-party WebAssembly in the app's policy

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland
**Amends:** the Content-Security-Policy of [ADR-0011](0011-the-router-and-its-readers.md), and the refusal of `'wasm-unsafe-eval'` on portalr's origin in [lattice RFC-0003](../../rfcs/0003-native-files-as-artifacts.md#alternatives)

## Context

Both UIs are served with one policy, `policy(site)` in `portalr/fastapi/ui.py`: `default-src 'self'`, `script-src 'self'`, `style-src 'self'`, `img-src 'self' data:`, `font-src 'self'`, `connect-src 'self'` and Supabase, `object-src 'none'`, `frame-ancestors 'none'`. It allows no inline script and no `eval`, and no WebAssembly, since compiling a module needs `'wasm-unsafe-eval'` (or `'unsafe-eval'`). It matters because supabase-js keeps the session in `localStorage` (lattice RFC-0002).

Lattice RFC-0003 refused `'wasm-unsafe-eval'` on portalr's origin. The case it weighed was reaching into WordCraft's unmodified browser build, 40 MB of WebAssembly from a third party, from a page on portalr's origin. It gave that editor an origin of its own instead.

[Lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md) puts Excalidraw's canvas directly in `app`, on portalr's origin, with its session and WebSocket (its O3). `@excalidraw/excalidraw` 0.18.1 holds two WebAssembly modules, harfbuzz and woff2, inlined as base64 in one lazily loaded chunk. It uses them to subset fonts for SVG export. The chunk graph shows nothing in plain editing importing that chunk; RFC-0006's spike checks this in Chromium. The owner decided (RFC-0006's O4) to allow WebAssembly in `app`, for first-party, pinned modules only, with the guardrails below. RFC-0006's spike still establishes whether plain editing needs it, or only export and conversion.

## Decision

- **`app`'s policy gains `'wasm-unsafe-eval'` in `script-src`,** for the whole of `app`. Nothing else in the policy changes. `'unsafe-eval'` stays absent, so `eval`, `new Function` and string timers are still refused; the directive allows compiling WebAssembly and nothing more.
- **admin's policy doesn't change.** `ui_router` sets each UI's policy from its name, instead of one for both. admin bundles no WebAssembly and doesn't need it.
- **Guardrails:**
  - **Modules ship only in our build.** Every WebAssembly module `app` may compile comes from a package in `bun.lock`, built by Vite into the wheel's `static/app/`. Nothing is fetched at run time from anywhere else: `connect-src` stays `'self'` and Supabase, and Excalidraw's font and asset path points at our own files, never at esm.sh.
  - **A test lists every module.** `web/wasm-allowlist.json` names each WebAssembly module in each UI's build: the package, the built file that holds it, and the SHA-256 of the module's bytes. The test finds modules both as `.wasm` files and inlined in JavaScript, by the `\0asm` magic and its base64 form (`AGFzbQ`), since 0.18.1 inlines its modules. It fails on a module not listed, a listed one missing, or a digest that changed. It runs in `portalr:check`, beside the size budgets. A module is added or its digest changed only in a reviewed change that says why, as a budget is raised ([ADR-0040](0040-scenarios-against-a-generated-application-and-size-budgets.md)).
  - **No third-party-hosted or agent-authored WebAssembly.** Nothing a model writes is compiled on portalr's origin; lattice RFC-0005's non-goal, no code from a model on portalr's origin, stands. Markdown is rendered without raw HTML ([ADR-0015](0015-the-chat-components-and-streamdown.md)), and a byte array in an artifact's data is never handed to `WebAssembly`.
  - **Mini apps get none.** RFC-0005's mini apps stay on their cookie-less origin, `apps.<host>`, whose proxy is served with `default-src 'none'` and no `'wasm-unsafe-eval'`. The inner frame inherits that policy. RFC-0005's phase 2 tests gain one case: `WebAssembly.compile` fails inside a mini app.
  - **The policy is tested exactly.** `tests/fastapi/test_ui.py` holds each UI's policy directive by directive, so a widening is a visible change.
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
