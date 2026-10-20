# ADR-0055: Every kind inline in its thread, and a native file read and edited there

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Amends:** [ADR-0052](0052-artifacts-inline-in-their-thread.md), where only a mini app was shown inline; and [ADR-0049](0049-checking-a-native-file-out-and-in.md), whose check-out opened the editor in a new tab only

## Context

[ADR-0052](0052-artifacts-inline-in-their-thread.md) put an artifact in the thread it was made in, through its kind's renderer, and showed only `app` there. A note, a form or a dashboard the agent made was a line in its answer and a link; a native file was a link to a page that reads it. The owner asked for every kind the app draws to be shown in the thread, fully, and usable there.

What exists for each kind:

| Kind | Renderer | What it can do in the thread |
|---|---|---|
| `note` | Markdown, with code, charts (Mermaid), math and images ([ADR-0015](0015-the-chat-components-and-streamdown.md)) | Read; its code copied |
| `form` | `SchemaForm`, sent through the page's `FormHost` | Filled in and sent, as the reader |
| `submission` | Its values, by field | Read |
| `dashboard` | `DashboardView`, its charts an add-on ([ADR-0044](0044-highlighting-and-math-on-demand.md)) | Read; its controls and a panel's form work |
| `app` | `AppFrame` ([ADR-0051](0051-mini-apps-the-sandboxed-frame-and-its-bridge.md)) | Run, as before |
| A native file's kinds | The manifest: name, type, size, outline ([ADR-0048](0048-native-files-in-the-app.md)) | See below |
| An application's own kind | JSON, unless the application gives a renderer | Its page |

Charts, code and images are parts of a note, not kinds. A tracker item is what a run filed, shown on the runs' pages ([ADR-0046](0046-tracker-links-on-runs.md)), not an artifact. A proposal is not an artifact either: the thread already shows its own with Accept and Reject.

A native file can't be drawn by the browser: its bytes are an office or a design file, which the portal never parses. Its app renders pages headless as PNGs, all but GridCraft, whose release renders none ([artifactr files ADR-0009](../../artifactr/files/adr/0009-each-crafting-app-declared-once-on-one-of-two-dialects.md)); the server keeps each version's text, which for a workbook is its sheets' cells, a tab between cells. Editing is a check-out ([ADR-0049](0049-checking-a-native-file-out-and-in.md)). Three apps' builds, GridCraft's, PdfCraft's and CADCraft's, take `?host=parent`, which lattice's shim on the editor's origin relays to the portal as `lattice:open`, `ready`, `save` and `dirty` ([files ADR-0010](../../artifactr/files/adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)); its action item for portalr, framing the shim, was still open. The others talk at level 1, save only.

## Decision

- **Every kind the kit draws is inline:** `markdown()`, `nativeFile()`, and artifactr.ui's `form`, `submission`, `dashboard` and `app` set `Renderer.inline`. A kind shown as JSON isn't; an application shows its own kind inline by setting the flag on its renderer.
- **The entry names its kind and has a full view,** in `InlineArtifact`, given a `kind` ("Note", "Form", "Word document"): the kind and the name above what is drawn, and "Full view", which makes the entry's box fill the window as a modal dialog (`aria-modal`, the page behind it inert, "Back to the page" focused first, Escape not already taken returns it, and focus goes back to "Full view"). The box isn't moved or drawn again, so a form's answers and a page's place are kept. `useFullView` and `inertOutside` are `ui`'s, which the app's frame now imports. An app, which names itself and has its own full view, is given no `kind`.
- **A form is sent from its thread,** as the reader: the thread's entry gives the renderers the `FormHost` the artifact's page gives, so a form and a dashboard's form panel are filled in and sent where they were made, under the same switches.
- **A native file is read in its thread, a page at a time:** `NativeInline`, in the app, reads the file's status, as its page does, and shows its size, pages and version, a download, and a view of it, chosen among what it has:
  - *Pages*, where the app renders them: `PageViewer`, one page at its width or the window's height, with the page before and after, Page Up and Down, Home and End, and the arrow keys, which go the other way in a page read right to left; "Actual size" scrolls it. A page is read when it is shown, so a long file costs one render at a time. A page being read is a page-shaped placeholder; one that fails says so, and that the file can still be downloaded.
  - *Cells*, for a workbook: its text read into sheets (`sheetsOf`, the outline saying which line names a sheet), each a `SheetTable` with lettered columns and numbered rows, the first 200 rows of a sheet, saying so where it has more; a sheet chosen by name.
  - *Outline* and *Text*: what the app read of it.
  It never shows the file's own bytes: no `<object>` for a PDF, whose route answers as an attachment under `CSP: sandbox` and `nosniff` ([files ADR-0007](../../artifactr/files/adr/0007-check-out-over-http-and-the-editor-on-its-own-origin.md)), and no SVG as an image, which VectorCraft renders. Where native files' routes aren't served, the entry is the manifest, as before.
- **Who has it, and checking it out, are the page's,** factored into `FileControls` and `useDownload`, which the page and the thread share: the holder, `CheckOut`, and, where its app is off in the workspace, that it is only read and downloaded.
- **A file whose app's build hands it over is edited in place,** where the status says `talk: bridged` and the deployment hosts its editor: "Edit here in GridCraft" checks it out and frames the shim, `/.lattice/shim.html` on the editor's origin, in the page (`sandbox="allow-scripts allow-same-origin allow-downloads allow-modals"`, no referrer). The page hears only that frame's window, from that origin, and listens from the moment the frame is put in the page, so a quick `ready` isn't missed. On `ready` it sends the checked-out version's bytes as `lattice:open`; `dirty` shows "Unsaved changes", and its close button says "Close without saving"; each `save` of the file's own extension is checked in as the reader, through the same route, and what came of it is said, after which the check-out has ended and the frame closes. A save in another format, such as an export, isn't checked in, and it says so. A build that says `failed`, or isn't ready within a minute, is said not to have started, with the download and the check-in beneath it as the way on. At level 1 nothing changes: the editor opens in a new tab, and the file is downloaded and checked in. No format is converted.
- **The portal frames each editor's origin:** `policy()` adds the origins of `Site.editors` to `frame-src`, beside the apps' origin. The shim answers only the portal it was made for, and the build's page is framed only by its own origin and the portal ([files ADR-0010](../../artifactr/files/adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)).
- **It is the thread's route chunk,** not an add-on: the app's bundle stays within its budget (initial 190.7 of 200 kB, total 481 of 520 kB).

## Options considered

### Option A: Every kind inline, files a page at a time, edited where their build hands the file over (chosen)

| Dimension | Assessment |
|---|---|
| Fit | Each kind as its page shows it, where it was asked for |
| Safety | No file is parsed by the browser; the editor is on its own origin, heard from that frame alone |
| Cost | One page rendered at a time; a frame a file being edited |

### Option B: The page's own section, as it is, in the thread

**Cons:** a strip of four pages and the check-in's controls are a page's, not a message's; on a phone they push the conversation off the screen.

### Option C: The browser's own viewers for PDFs and SVGs

**Cons:** the content route serves a file as an attachment under a sandboxing policy, so the portal's origin never runs or draws an upload; a viewer would need a route that does, and would draw only two of the kinds.

### Option D: Edit every app's files in place

**Cons:** six builds have no host surface, and three a JavaScript API no pilot has run through the shim; framing them gains nothing over a new tab, and would hide that the file goes through the person's disk.

## Trade-off analysis

The thread shows what each kind's page shows, as far as a message can hold it: its content, or for a file a page at a time and its cells, and the actions people take on it. Editing in place is offered only where the build hands the file over, which three releases do; the others keep the honest download-edit-upload.

## Consequences

- Easier: a note, a form, a dashboard and a file the agent makes are read and used where they were asked for; a workbook is read without GridCraft rendering it.
- Easier: an application's own kind is shown inline by one flag.
- Harder: a thread with many files reads each one's status, and a page of each, as it is shown.
- Harder: the portal's policy frames each hosted editor's origin, which a deployment names in `Site.editors`; an editor hosted without its shim isn't ready, and says so.
- Revisit: a JavaScript API's apps (FilmCraft, EffectCraft, LightCraft) in place, once a pilot runs one through the shim; FreeCAD's `cad_model` and Blender's files, by their own talk levels, once they are native files; a version's pages compared in the thread, which its page does.

## Action items

1. [x] `inline` on every kit renderer; `InlineArtifact`'s kind and full view; `useFullView`.
2. [x] `NativeInline`, `PageViewer`, `SheetTable`, `FileControls` and `useDownload`.
3. [x] `EditorFrame`, `CheckOut`'s "Edit here", and the editors' origins in `frame-src`.
4. [ ] stackr's template: native files' routes and a hosted editor, so a generated application shows a file inline out of the box.
