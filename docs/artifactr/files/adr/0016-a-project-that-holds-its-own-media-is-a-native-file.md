# ADR-0016: A project that holds its own media is a native file, and an export is not kept

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Amends:** [ADR-0009](0009-each-crafting-app-declared-once-on-one-of-two-dialects.md), which declared FilmCraft, EffectCraft, SoundCraft and LightCraft export only, and FilmCraft's browser build as having a JavaScript API

Settles what lattice keeps of the four crafting apps [ADR-0009](0009-each-crafting-app-declared-once-on-one-of-two-dialects.md) called export only, "whose projects point at media outside them", under [lattice RFC-0003](../../../rfcs/0003-native-files-as-artifacts.md).

## Context

On 2026-10-20 we ran each app's pinned CLI on macOS, headless, on files it made itself and on files made to break it, and grepped each pinned browser build:

- **FilmCraft 0.8.0** edits video. Its project, `.fcproj`, is JSON that says `"format": "filmcraft.project"` and its `schema_version`, 15. An imported file is named in it by absolute path, as is a proxy and a LUT read from a file; bars and tone, mattes, black video, titles, shapes, captions and its demo footage are generated, held in the project itself. Its server is the `commands` dialect's, on the one project open: `file.open` says how many media are missing and whether it migrated an older schema; it refuses a newer schema, and a frame size it can't hold, as damaged. It renders the active sequence's frame at a time as a PNG, and exports H.264, HEVC, ProRes, DNxHR and more, WAV, AIFF and AAC, and stills. Two saves of a project, in two processes, are the same bytes. Its CLI confines nothing, and reads and writes any path a command names. Its browser build exports `start` and two loader hooks, and no API a host can call.
- **EffectCraft 0.11.1** makes motion graphics. Its project, `.ecproj`, is JSON whose items are compositions, solids, folders, and footage, named by path. Its server is the `commands` dialect's too, and takes a read and a write root, which it holds: a file outside them is refused, and so is its JavaScript, `script.run`, while it is confined. It renders a composition's frame as a PNG, headless, and renders video, image sequences and audio. Two saves are the same bytes. Its browser build has a JavaScript API, `window.effectcraft`.
- **SoundCraft 0.8.0** records and mixes audio. Its session, `.scraft`, is JSON; its audio, recorded, imported or loaded into its sampler, is its `sources`, which a save writes as files in an `Audio Files` folder beside the session, so a session with audio is a folder, not a file. MIDI and its built-in instruments are held in the session itself. Its server is the `tools` dialect's, with a read and a write root. It renders no page headless: its screenshot needs the desktop app, and its mix-down, `bounce_mix`, is audio. Two saves are the same bytes. Its browser build has no API a host can call.
- **LightCraft 0.8.0** develops photos. Its library is a folder, and it never writes a photo it develops: an edit is kept in the library, or in an XMP sidecar beside the photo. Its DNG export is rendered, linear and demosaiced, with the edit baked in, and opened again holds no develop settings at all. So no one file carries a photo and its edit back to LightCraft. Its CLI confines nothing; it renders a photo headless, and its browser build has a JavaScript API, `globalThis.lightcraft`.

## Decision

- **The native file of FilmCraft, EffectCraft and SoundCraft is its project, kept only whole.** Each is a type of its own, its media type of lattice's naming as FigCraft's is: a video project, `VideoProject` (`.fcproj`, `FCPROJ`, `application/x-fcproj`); motion graphics, `MotionGraphics` (`.ecproj`, `ECPROJ`, `application/x-ecproj`); an audio session, `AudioSession` (`.scraft`, `SCRAFT`, `application/x-scraft`). Their `reach` is `file`. A project that draws on anything outside it is refused, by name, before its app opens it, and after every save, so a batch that imports a file is refused whole: FilmCraft's media that aren't its generators', a proxy, and a LUT that isn't one of its own, `builtin:`; EffectCraft's footage; SoundCraft's sources and video. FilmCraft's own word on the open, media missing or a migrated schema, refuses it too: a save would change it.
- **An export is not kept.** What an app renders or exports from a project, a video, an image sequence, a mix-down, is made from the project and is lossy, large, or both. The `App` port has no export, and no check-in converts a project into one ([ADR-0012](0012-an-app-for-each-type-and-no-format-changed-by-a-check-in.md)). Keeping an export, as an artifact of its own made from a project's revision, is later work.
- **A page is a second.** FilmCraft's and EffectCraft's pages are the seconds of the active sequence or composition, each drawn as the frame at its start; a project with none has no page. SoundCraft renders none headless, so its sessions have no page.
- **LightCraft stays export only, with no adapter.** Its work is a library and sidecars, never one file; a photo alone would be a read-only file whose edits lattice couldn't keep, and its RAW decoders' attack surface for no edit. Its key stays off.
- **No media is decoded in lattice's process.** An adapter reads a project as JSON, once a call, refused past 2 MiB (the apps' own demo projects are 30 KB to 730 KB), or nested past the depth pydantic's parser reads; a project of tiny values at that limit, the most work to read, parses in a fifth of a second into some 90 MB, and each app's hostile files hold one, `dense`. It reads no image, video or audio. Only the app's CLI decodes, under the worker's limits on hostile files ([ADR-0013](0013-the-worker-runs-each-call-under-limits-behind-a-token.md)). EffectCraft's and SoundCraft's projects are told by their JSON's shape alone, `savedBy` and `schema`, `format_version` and `tracks`, as neither names its format.
- **What a project draws from outside is read by what it may hold.** FilmCraft's items are sequences, graphics and media, and anything else is refused, as is EffectCraft's that isn't a composition, solid or folder. Of FilmCraft 0.8.0's 303 effects, its `effects.list` gives only its colour effect's two LUTs a parameter that names a file. SoundCraft's plugins are read from the fields that name one, `plugin` and `instrument`, however their format is cased.
- **A batch reaches nothing past its project.** FilmCraft's CLI confines nothing, so its adapter runs no command that opens, saves, imports or exports a file, or reaches its user's presets, shortcuts, LUT library or media, and no command given a `path`, `paths`, `file`, `folder` or `dir`; a LUT named by a parameter's value is refused after the save. That FilmCraft can't reach past the call's directory is not tested here: run it in the worker on files you don't trust. SoundCraft's runs none of its engine's or app's commands. A project's pages are at most 10,000, whatever its duration says.
- **EffectCraft's expressions are JavaScript, run by the Boa engine inside its CLI** at render, under a limit on their loops of its own. That limit isn't confinement: EffectCraft's roots confine what its file commands reach, and the worker's limits what the CLI as a whole takes; an expression is a project's own code, so a project from someone you don't trust runs in the worker.
- **Linux is proven in part.** On Linux x86_64 each corpus file is made again byte for byte, kept, a fixpoint, and its frames render; Linux aarch64, and Nightly's runner, are shown by its first run.
- **FilmCraft's browser build has no host surface,** which ADR-0009 recorded as a JavaScript API: its `bridge` is none, corrected in place. Each app's talk level stays `save` ([ADR-0010](0010-a-shim-beside-the-build-and-talk-level-one-plus.md)).
- **Each corpus is made by its app.** These projects hold every field their apps write, too many to write by hand and still be read, so each feature's file is what its adapter saves of a script of the app's own commands on a blank project, and the live tests hold the committed files to what the pinned release makes. Each app's hostile files are refused within their deadline: a project too large, nested too deep or not JSON, media and LUTs at a path or up the tree, and, as the app reads them, a newer schema, an older one, and a frame or composition too large.

## Options considered

### Option A: The project, kept only whole (chosen)

| Dimension | Assessment |
|---|---|
| Fit | Each app opens, edits and saves its own project, as every other app's native file |
| Safety | No path outside a project is read; the CLI decodes the media it generates, and nothing else |
| Cost | A project with imported media can't be kept |

### Option B: The export, kept as a read-only file

**Cons:** a render is lossy and large, and no app edits it back into its project; every hostile video, audio file and RAW would reach a decoder, for a file no one edits.

### Option C: The project and its media, in one package

**Cons:** no app opens such a package, so every check-out and check-in would convert it; and every file it held would be a hostile medium to decode.

## Trade-off analysis

A project that holds its own media is a small JSON file that its app edits, renders and saves byte for byte, which is what a native file is. One that names media outside it can't be kept as one file, and keeping its media would make lattice a store of hostile video and audio for every one of them. A video made only of titles, mattes and captions, a motion graphic of shapes and text, and a session of MIDI and the built-in instruments are what the first round keeps.

## Consequences

- Easier: three more apps' files are native files, with their own adapters, corpora and Nightly runs, on the dialects ADR-0009 built.
- Harder: a project that imports media is refused, by name; its people keep it outside lattice.
- Revisit: keeping an export as an artifact made from a project's revision; keeping a project's media as blobs of their own, beside it; LightCraft, once a release writes its edit into one file; each JavaScript API's level, with a pilot through the shim.

## Action items

1. [x] FilmCraft's adapter, `VideoProject`, its corpus and hostile files, and its Nightly run.
2. [x] EffectCraft's adapter, `MotionGraphics`, its corpus and hostile files, and its Nightly run.
3. [x] SoundCraft's adapter, `AudioSession`, its corpus and hostile files, and its Nightly run.
4. [ ] Exports as artifacts of their own.
