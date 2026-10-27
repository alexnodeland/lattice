# ADR-0055: Every kind inline in its thread, and a native file read and edited there

**Status:** Accepted
**Date:** 2026-10-20
**Deciders:** Alex Nodeland
**Note:** ADR-0053 is the chat's questions and ADR-0054 readable revisions (#431), decided beside this one.
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
  - *Pages*, where the app renders them: `PageViewer`, one page at its width or the window's height, with the page before and after, Page Up and Down, Home and End, and the arrow keys, which go the other way in a page read right to left; a key with a modifier is left to the browser, and at "Actual size" the arrows scroll the page, as a scrolled region's do, while Page Up and Down, Home and End still page. A page is read when it is shown, so a long file costs one render at a time. A page being read is a page-shaped placeholder; one that fails says so, and that the file can still be downloaded.
  - *Cells*, for a workbook: its text read into sheets (`sheetsOf`, the outline saying which line names a sheet), each a `SheetTable` with lettered columns and numbered rows, the first 200 rows and 50 columns of a sheet, as wide as the rows shown, saying so where it has more; a sheet chosen by name. The text has no escapes, so a cell holding a tab or a line break reads as two cells or two rows there; the downloaded file has it whole.
  - *Outline* and *Text*: what the app read of it.
  It never shows the file's own bytes: no `<object>` for a PDF, whose route answers as an attachment under `CSP: sandbox` and `nosniff` ([files ADR-0007](../../artifactr/files/adr/0007-check-out-over-http-and-the-editor-on-its-own-origin.md)), and no SVG as an image, which VectorCraft renders. Where native files' routes aren't served, the entry is the manifest, as before.
- **Who has it, and checking it out, are the page's,** factored into `FileControls` and `useDownload`, which the page and the thread share: the holder, `CheckOut`, and, where its app is off in the workspace, that it is only read and downloaded.
- **A file whose app's build hands it over is edited in place,** where the status says `talk: bridged` and the deployment hosts its editor: "Edit here in GridCraft" checks it out and frames the shim, `/.lattice/shim.html` on the editor's origin, in the page (`sandbox="allow-scripts allow-same-origin allow-downloads allow-modals allow-forms"`, `allow="clipboard-read; clipboard-write"`, no referrer; `allow-popups` stays, as the pilot builds open a link in a new tab with `window.open(url, "_blank")`, eframe's way, which would otherwise be dropped without a word), never on the portal's own origin, which the frame refuses whoever named it, and never on the apps' or Supabase's, which `Site` refuses, comparing scheme, host and port with the default ports filled in. `Site` isn't told the portal's own origin, so that one is refused in the UIs. The page hears only that frame's window, from that origin, at most 50 messages a second, and listens from the moment the frame is put in the page, so a quick `ready` isn't missed. On `ready` it sends the version the check-out holds as `lattice:open`. A `dirty` that is a boolean shows "Unsaved changes"; while there are any, closing is confirmed, leaving for another of the app's pages is asked about (a router blocker), closing or reloading the tab is guarded (`beforeunload`), and a check-out with under fifteen minutes left is extended, a refusal said once. Each `save` of the file's own extension, within the check-in's limit, is checked in as the reader, one at a time, and what came of it is said; once one is in, the check-out has ended and the frame closes. A refusal (someone else's check-out, a lapsed one, a conflict) leaves the editor open with the work in it. A save in another format, such as an export, or past the limit, isn't checked in, and it says so. **One file is edited in place on a page at a time:** another opens only once the first has no unsaved changes, and opening it closes the first; the place is asked for before the file is checked out, so no file is held for an editor that can't open. The page knows of unsaved changes from the build's `dirty`, which it hears as it is sent: a change made in the moment before the first editor is closed, and not yet said, is lost with it. Switched off while it is edited, the editor stays, and says a save won't be checked in, so the work can be downloaded from it. A build that says `failed`, or isn't ready within a minute, is said not to have started, with the download and the check-in beneath it as the way on. At level 1 nothing changes: the editor opens in a new tab, and the file is downloaded and checked in. No format is converted.
- **In a thread, the preview and the editor are one box that flips** (the owner's word: not a preview with an editor stacked under it). Where the file's build hands it over and its editor is hosted, the entry's box has the editor's height in both states, and "Edit in GridCraft", beside the preview's views, checks the file out and turns the box into the editor; "Back to preview" turns it back. The preview is hidden, not taken down, so its page, its zoom and its view are as they were; after a save it shows the new version, as every read follows the log. The turn is 200 ms, and none where motion is reduced; it moves onto ADR-0057's motion tokens with their foundation work. FreeCAD's `cad_model` is read inline as every native file is. On the file's own page the editor is still drawn beside its controls. Download, who has it, and the check-in by upload stay below the box. An app without a hosted editor has the preview alone, with no switch.
- **What going back does to the check-out:** back with no unsaved changes tries to let the check-out go, and the editor stays in its place, with the switch to edit held, until that is answered. There is no route that only ends a check-out, so letting it go is a check-in of the file's head as it is: it changes nothing and makes no version. It is the head, not the version opened, so a lease that lapsed while the file moved on gives "unchanged" and never a proposal to put the old version back. A check-out found checked in already has ended too. Any other refusal is said, and the check-out holds until it runs out (eight hours) or is checked in. Back with unsaved changes asks: "Keep editing", or "Discard and go back". There is no "Save and go back": at talk level 1+ the page can't tell the build to save, so it says to save in the app first. While a save is being checked in, going back isn't offered, so it can't race the save. The router blocker asks only on a change of page, not of search or hash, and covers the browser's own back and forward within the app (checked in Chromium against GridCraft's build; the tests' memory history moves without asking). Leaving the app by back or forward, or closing the tab, falls to the `beforeunload` guard, which a browser may show only once the person has acted in the portal's own page, not only inside the editor's frame; the `beforeunload` guard and one editor at a time stay as they are. Opening another file's editor while the first has no unsaved changes closes the first without letting its check-out go: it holds until it runs out or is checked in, as from the file's page. The flip moves the focus to the side turned to, and turns only on a flip, not as the box is first drawn.
- **The portal frames each editor's origin:** `policy()` adds the origins of `Site.editors` to `frame-src`, beside the apps' origin. The shim answers only the portal it was made for, and the build's page is framed only by its own origin and the portal ([files ADR-0010](../../artifactr/files/adr/0010-a-shim-beside-the-build-and-talk-level-one-plus.md)).
- **A file is read once it comes near the window,** 600 pixels out, and its status polled only while it is near; a page is read only when it is shown, and the next only when asked for. An entry not yet near holds a placeholder, so printing the thread or finding in it doesn't reach a file's outline until it has been scrolled to.
- **It is the thread's route chunk,** not an add-on: the app's bundle stays within its budget (initial 191.8 of 200 kB, total 497.8 of 520 kB, on a fresh build).

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
- Harder: a thread with many files reads each one's status, and a page of each, as each comes into sight; one editor runs at a time.
- Harder: "every kind inline" holds for the portal; a generated application shows a native file as its manifest only until stackr's template wires native files' routes, a worker and a hosted editor (action item 4).
- Harder: work done only inside the editor's frame may not count as the person acting on the portal's page, so a browser can let the tab close without asking; the router blocker still asks within the app.
- Unverified in a frame of its own: `sessionStorage` refused, as in a private window, forgets a check-out on reload; the lease still names it while it holds.
- Harder: the portal's policy frames each hosted editor's origin, which a deployment names in `Site.editors`; an editor hosted without its shim isn't ready, and says so.
- Revisit: a JavaScript API's apps (FilmCraft, EffectCraft, LightCraft) in place, once a pilot runs one through the shim; FreeCAD's `cad_model` and Blender's files, by their own talk levels, once they are native files; a version's pages compared in the thread, which its page does.

> **Amended (2026-10-27) by [ADR-0083](0083-several-portal-origins-an-allow-list-aliases-and-a-union-policy.md):** the editors the page frames are those beside the address it is at, `deploymentAt(config, location.origin)`, the canonical ones at the portal's own origin or where none is named; `frame-src` names the editors' origins of every alias too; and `EditorFrame` adds `?host=<location.origin>` to the shim's URL, so a shim told several portals knows which one frames it. At an address the deployment names no place for, a file is read and downloaded, and not edited in place.

## Action items

1. [x] `inline` on every kit renderer; `InlineArtifact`'s kind and full view; `useFullView`.
2. [x] `NativeInline`, `PageViewer`, `SheetTable`, `FileControls` and `useDownload`.
3. [x] `EditorFrame`, `CheckOut`'s "Edit here", and the editors' origins in `frame-src`.
4. [ ] stackr's template: native files' routes and a hosted editor, so a generated application shows a file inline out of the box.
