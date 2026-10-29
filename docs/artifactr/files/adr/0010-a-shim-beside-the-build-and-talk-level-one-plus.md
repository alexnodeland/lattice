# ADR-0010: A shim beside the build, on the editor's origin, and talk level 1+

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland
**Amends:** [ADR-0007](0007-check-out-over-http-and-the-editor-on-its-own-origin.md), whose editor no page could frame

## Context

[ADR-0007](0007-check-out-over-http-and-the-editor-on-its-own-origin.md) serves an app's browser build, as released, on an origin of its own, with `frame-ancestors 'none'`: a person downloads the checked-out file, opens it in the build, saves it and uploads it. Three released builds have more: GridCraft 0.8.0, PdfCraft 0.8.0 and CADCraft 0.8.0 take `?host=parent`, a `postMessage` bridge on which the page that frames the build opens a file in it (`<app>:open`) and hears when it is ready, each file it would download (`<app>:save`), and whether it has unsaved changes (`<app>:dirty`). EffectCraft and LightCraft put a JavaScript API on the build's window instead (FilmCraft's 0.8.0 build has none, corrected 2026-10-20 by [ADR-0016](0016-a-project-that-holds-its-own-media-is-a-native-file.md)).

Each surface answers only a page of the build's own origin: the bridge hears and answers only its parent window on that origin, and the API is a global of the build's page. The portal is on another origin, and lattice neither forks the builds nor contributes to them.

## Decision

- **A shim of lattice's own, beside the build:** `editor_app(build, craft=craft, portal=origin)` also serves `/.lattice/shim.html` on the editor's origin. The portal frames the shim; the shim frames the build, on its own origin, with `?host=parent` for a bridge; and the shim relays between them by `postMessage`. Every message is checked for its window and its origin: from the portal, only `window.parent` at the configured origin; from the build, only the shim's own frame at its own origin. The build is served unchanged.
- **One protocol to the portal, whatever the build's surface:** `lattice:open` `{ name, bytes }` to the shim, and `lattice:ready`, `lattice:save` `{ name, bytes }`, `lattice:dirty` `{ dirty }` and `lattice:failed` `{ error }` from it. For a JavaScript API, `lattice:call` `{ id, method, args }` calls one of the methods the deployment allows (`editor_app(..., methods=)`) on the build's global, and `lattice:reply` answers it; any other method is ignored.
- **The shim forwards every save, whatever its format.** The bridges hand over every file the build would download: GridCraft's Save of a workbook opened from `.csv` is a `.xlsx`, and its exports are PDFs. The shim forwards each with its name; the check-in decides, and refuses a format other than the checked-out one.
- **Policies.** The shim runs its own script and style by their hashes, frames only its own origin, loads nothing else, and is framed only by the portal (`frame-ancestors <portal>`). With a shim, the build's page may be framed by its own origin and the portal (`frame-ancestors 'self' <portal>`), since a browser checks every ancestor of a frame, the top one too; without one, it is `'none'`, as before. The portal's own policy must let it frame the editor's origin, which is portalr's to set.
- **Talk level 1+, named `bridged`,** for an app whose build has a `?host=parent` bridge: the host opens the file in the person's editor and hears each save and whether there are unsaved changes, and sends no commands. It is not RFC-0003's level 2. `Talk` gains `bridged`, and `Headless.talk` is `bridged` for GridCraft, PdfCraft and CADCraft, `save` for the rest. A JavaScript API could carry commands with replies, but none has been run through the shim, so none is claimed; an app's level is raised when its own pilot has run.
- **The pilot was run by hand,** in Chromium, with the editor on `127.0.0.1` and a stand-in portal on `localhost`, a different origin. GridCraft 0.8.0 through the shim: `ready` with its version, a `.csv` opened by `lattice:open`, a cell edited, `dirty` true, Save handed over as `figures.xlsx` (4,112 bytes), `dirty` false, and no policy violation. PdfCraft 0.8.0: `ready`, a PDF opened, and Save handed over. CADCraft 0.8.0: `ready`, a DXF opened, a line drawn, `dirty` true, Save handed over as `plan.dxf`, `dirty` false. The first run found that `frame-ancestors 'self'` on the build blocked it inside the portal, which the policy above fixes.

## Options considered

### Option A: A shim of lattice's own on the editor's origin (chosen)

| Dimension | Assessment |
|---|---|
| Fit | Reaches every surface the builds have, as released |
| Isolation | The portal and the build share no origin; the shim checks every message |
| Cost | A page, its script, and a frame the portal shows |

### Option B: Keep level 1: download, edit, upload

**Cons:** the person carries the file through their disk, for apps whose builds can hand it over.

### Option C: The build on the portal's origin

**Cons:** the build's code would run beside the portal's token, which ADR-0007 keeps apart.

## Trade-off analysis

The shim is the only route above level 1 that changes no build and puts none on the portal's origin. What it costs is a page of our own on the editor's origin, held to a policy as strict as the build's.

## Consequences

- Easier: portalr can open a check-out in the editor, show whether it has unsaved changes, and check in each save, for GridCraft, PdfCraft and CADCraft.
- Harder: the editor's origin serves our code as well as the build's, so its policy and its messages' checks are ours to keep.
- Revisit: a JavaScript API's level, with each of EffectCraft's and LightCraft's pilots; a build whose bridge gains commands; portalr's frame and policy for the editor, its own work.

> **Amended (2026-10-26):** WordCraft 0.11.0 has the `?host=parent` bridge (`storytold/wordcraft#3822`): `wordcraft:ready`, `wordcraft:open`, `wordcraft:save`, `wordcraft:dirty` and `wordcraft:failed`, as GridCraft's, PdfCraft's and CADCraft's. So `Headless.talk` is `bridged` for it too, and its check-out opens in the portal's frame. The bridge answers only a parent on the page's own origin, so the shim, not the portal, is its parent; framed by a page of another origin, it stays off. FilmCraft's 0.8.0 build does have a JavaScript API, `window.filmcraft` (see [ADR-0016](0016-a-project-that-holds-its-own-media-is-a-native-file.md)), which this ADR's context denied.
>
> Run by hand in Chromium, the editor on `127.0.0.1:8766` and a stand-in portal on `127.0.0.1:8765`, a different origin:
>
> - `ready` came with `0.11.0`.
> - A `.docx` opened by `lattice:open`; an edit made `dirty` true.
> - Ctrl+S handed over `text.docx` and `dirty` was false; File, Save As, Browse handed over `text.docx` again, under its own name, with no picker.
> - A `.md` opened and edited was handed over as `note.md` on Ctrl+S, and the build stayed dirty; the check-in would refuse another format in any case ([ADR-0012](0012-an-app-for-each-type-and-no-format-changed-by-a-check-in.md)).
> - Framed directly by the stand-in portal, the build sent nothing and opened nothing.
> - File, Open, Browse still opens the build's picker, whose inline stylesheet a policy without `'unsafe-inline'` blocks, so [ADR-0007](0007-check-out-over-http-and-the-editor-on-its-own-origin.md)'s allowance of inline styles stays.

> **Amended (2026-10-27) by [portalr ADR-0084](../../../portalr/adr/0084-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md):** `shim_page` and `shim_policy` take the portal's origin or each of its origins; the page names them all in `data-portals`, the policy's `frame-ancestors` too, and the script learns which one frames it from `?host=`, which the portal's frame adds: with one portal it needs none, with several it takes only a `?host=` among them, and without one does nothing, the build not even loaded. The chosen portal is still the only origin it posts to and hears from. The lax origin check is `lattice_core.origins.web_origin`'s, so plain http is refused off loopback.

> **Amended (2026-10-28):** every pinned browser build was surveyed for the bridge, and every latest release besides. Only WordCraft 0.11.0, GridCraft 0.8.0, PdfCraft 0.8.0 and CADCraft 0.8.0 have one: their wasm-bindgen glue imports `window.postMessage` with a target origin, and three of them name their own `apps/<app>-web/src/host.rs`. DeckCraft 0.7.0, PhotoCraft 0.9.0, VectorCraft 0.12.0, DesignCraft 0.9.0, FigCraft 0.6.0, FilmCraft 0.8.0, EffectCraft 0.11.1 and SoundCraft 0.8.0 have none, nor do their releases of 2026-10-28 (DeckCraft 0.12.0, PhotoCraft 0.17.0, VectorCraft 0.18.0, DesignCraft 0.14.0, FigCraft 0.12.1, FilmCraft 0.14.0, EffectCraft 0.18.0, SoundCraft 0.14.0), and each has an open issue upstream asking for one. EffectCraft's `window.effectcraft` takes a file in (`addFile`) but hands no save back and says nothing of unsaved changes, so the shim can't carry a check-in through it; FilmCraft's likewise. FreeCAD and Blender release no browser build. So the template hosts an editor for the four alone, and copier.yml says of each other app why it has none (`no_editor`), which scripts/check-template and artifactr's registry tests hold; the portal says plainly that such an app can't be edited in its window. Each missing bridge, with its upstream issue, is tracked in lattice#1107; nightly's Fidelity job holds the registry's `bridge` to each pinned build, so a release that gains one fails there until its editor is wired.

## Action items

1. [x] `shim_page`, `shim_policy`, and `editor_app(build, craft=, portal=, methods=)`.
2. [x] `bridged`, and `Headless.talk` by the build's surface.
3. [x] portalr: frame the shim, open the check-out in it, and check in its saves ([portalr ADR-0055](../../../portalr/adr/0055-every-kind-inline-and-a-native-file-read-and-edited-in-its-thread.md)).
