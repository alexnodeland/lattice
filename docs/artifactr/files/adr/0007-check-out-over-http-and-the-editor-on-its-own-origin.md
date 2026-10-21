# ADR-0007: Check-out over HTTP, and the editor on an origin of its own

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records the server side of phase 4 of [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md#people-check-out-and-check-in): the routes a person checks a file out and in through, and how the app's browser build is served.

## Context

WordCraft's browser build talks at level 1: it opens a file from a picker and saves one through the File System Access API or a download. Its host bridges, `storytold/wordcraft#405` and `#1655`, were still open and unmerged on 2026-10-17, and lattice neither forks nor contributes. So a person downloads the file, edits it in the hosted build, saves it, and uploads it. RFC-0003 puts the routes in `files_router`, beside artifactr's, with the same `resolve_actor`, and every route names an artifact and a revision, never a bare digest. It serves the build on an origin of its own, under a policy that lets it reach nothing else.

## Decision

- **`files_router(workspaces, files, resolve_actor=, limit=)`,** with the `fastapi` extra, mounted beside `artifactr_router`:
  - `GET /workspaces/{w}/files/{a}`: the head's name, type, size, outline and pages; whose check-out holds its lease, by participant (none for an agent's edit), and until when, never the lease's holder as stored; the app's talk level; and whether the app is on in the workspace.
  - `POST /workspaces/{w}/files/{a}/checkouts` (201): a check-out, as `NativeFiles.check_out` makes it.
  - `POST /workspaces/{w}/checkouts/{c}/extension`: the check-out, extended.
  - `PUT /workspaces/{w}/checkouts/{c}/file`: the edited file as the body, streamed into the blob store; it answers `applied` with the version, `proposed` with the proposal for a stale check-in, or `unchanged`.
  - `GET /workspaces/{w}/files/{a}/versions/{v}/content`: a version's bytes, as an attachment with the file's name, never sniffed (`nosniff`), never run as a page (`Content-Security-Policy: sandbox`) and never cached (`private, no-store`), since they are an upload served on the portal's origin.
  - `GET /workspaces/{w}/files/{a}/versions/{v}/pages/{p}`: a version's page, rendered by the app, as a PNG.
- **Its statuses are artifactr's,** for every rejection (`not_enabled` and a busy file are 409, someone else's check-out 403, a hidden file 404), and the app's own: a file it refuses is 422, and so is a page past its end, one too large 413, and a timeout or a crash 503; the OpenAPI document lists each. A body whose `Content-Length` passes `limit`, which an application sets to its blob store's (25 MiB by default, as the store's), is refused before it is read, and one that grows past the store's limit as it streams is refused there. Each request's span is attributed as artifactr's router's are.
- **Its OpenAPI document is committed,** as `schemas/artifactr-files.openapi.json`, and a test holds it to the router.
- **`editor_app(build)` serves the build unchanged,** with headers only: a Content-Security-Policy of `default-src 'self' blob:`, scripts from its own files and its inline script by its SHA-256, with `'wasm-unsafe-eval'`, workers from its own files only, styles inline, images from itself, `blob:` and `data:`, and no plugin, base, form or frame ancestor; `nosniff`, no referrer, `Cross-Origin-Resource-Policy` and `Cross-Origin-Opener-Policy` of `same-origin`, so the portal's window and the editor's hold no handle on each other; the page, and anything not found, revalidated, and the `.js` and `.wasm` it serves cached for good, which WordCraft's build names by their hashes. The application serves it on a host name of its own, for which the portal sets no cookies.
- **Styles are allowed inline,** where RFC-0003 named only the inline script's hash: WordCraft's file picker (`rfd`) adds a stylesheet of its own as it opens, whose text is in the WebAssembly, and the build is never changed to hash it. A style runs no code, and anything it could load is held to the build's own origin by the rest of the policy.
- **The pilot was run by hand** in Chromium against v0.7.0, served by `editor_app` on 127.0.0.1: the build loaded with no policy violation and requested only its own four files; it opened a corpus file through its picker, took an edit, and saved it as a download, which the corpus' reader read back with the edit. The download was had by removing the File System Access API from the test's page, so the build fell back to it; a person picks where the file goes.
- **Nightly runs the pilot's server side** with WordCraft itself: the build served under its policy, and a check-out over HTTP, downloaded, edited by the headless CLI, which shares the browser build's engine, and checked in, then checked in again as a retry that changes nothing.

## Options considered

### Option A: Routes beside artifactr's, and the build on its own origin (chosen)

| Dimension | Assessment |
|---|---|
| Fit | RFC-0003's level 1, through an unmodified build |
| Isolation | The editor holds no token and reaches no other origin |
| Cost | Download, edit, save and upload: clunky, as the RFC says |

### Option B: The build in a frame of the portal

**Cons:** without a host bridge, a frame gains nothing but a shared origin's risks; RFC-0003 rejects reaching into the build.

## Trade-off analysis

Level 1 is what the unmodified build offers. The routes and the editor prove the lease, the hosting and the check-in, and a host bridge, once one ships in a release, changes only how the bytes travel.

## Consequences

- Easier: a person can check a file out and in today, with WordCraft as released.
- Harder: an application hosts a second origin, and a 40 MB build on it.
- Deferred: portalr's renderer, its previews and diffs, its check-out and check-in screens, and the `bdd` scenarios that drive them; and stackr's hosting of the build at its edge, with the pin check against the worker's image.
- Revisit: the talk level, and these routes' check-in, when WordCraft's host bridge lands in a release.

## Action items

1. [x] `files_router`, its OpenAPI document and its tests.
2. [x] `editor_app` and `editor_policy`; the pilot run by hand, and its server side nightly.
3. [x] portalr's renderer, previews, diffs, check-out and check-in, with `bdd` scenarios.
4. [ ] stackr: the build at the edge, on its own host name. A generated application serves each bridged app's build on a loopback port of its own ([stackr ADR-0043](../../../stackr/adr/0043-native-files-in-the-template.md)); a single host's edge, with host names and TLS, doesn't yet.
