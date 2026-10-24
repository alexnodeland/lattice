# ADR-0074: Editing a diagram on its canvas, and the images put on it

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland

Records portalr's half of [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 3b, which [ADR-0072](0072-a-diagrams-card-and-its-canvas-to-look-at.md) left for after the canvas to look at: drawing on a diagram's canvas, and putting an image on it. It sends the element-scoped patch of [artifactr ADR-0086](../../artifactr/adr/0086-diagrams-data-an-element-scoped-patch-and-its-checks.md), and uploads images to the route of [artifactr ADR-0092](../../artifactr/adr/0092-a-diagrams-images-uploaded-by-a-person-and-read-where-it-names-them.md).

## Context

- **The canvas only showed a diagram** (ADR-0072). Every key, drop, paste and menu that would change it was refused at its edge.
- **Every writer sends one shape of edit.** The agent's tools write a JSON Patch per element: a `test` of the version it had and a `replace`, an `add` for a new one, never a `remove`, and an `add` under `/files/{digest}` for a new image (artifactr's `element_patch`). A person's edit must be the same, so the checks hold it as they hold the agent's.
- **The first load has no room.** The app's initial was 202,761 bytes of its 203,000; whatever editing needs must be in the `canvas` add-on, or reach the first load through nothing new.
- **Excalidraw's image path reaches for pica and image-blob-reduce**, which ADR-0072 refused: their `require`s would put the bundler's helper in the runtime every chunk shares, and pica brings WebAssembly and a worker made from a `blob:` URL.
- **A diagram is anyone's in the workspace to write.** Its elements may hold links, embedded pages, and images named by anything.

## Decision

### Edit mode

- **The canvas opens to look at, as before.** Where the page says which diagram it shows and at which version, lets the person reach the workspace, and grantr says they may `artifactr:edit_artifact` on the diagram, it offers **Edit**. A viewer is offered none; one whose grants change while it is open is refused when they save, and the canvas says so.
- **In edit mode, the canvas keeps what it never takes:**
  - no link: each element's `link` is cleared as the canvas takes it and as it saves it; Excalidraw's link shortcut (⌘K) is refused, and its link button and editor aren't shown;
  - no embedded page: an `embeddable` or `iframe` element is neither drawn nor saved, and a link pasted embeds nothing (`validateEmbeddable={false}`);
  - no library, which browses and imports from libraries.excalidraw.com, and none of its further tools (an embedded page, Mermaid's converter, frames, the laser): their buttons aren't shown;
  - an image only where the diagram names its bytes by a SHA-256 digest, read over artifactr's route; an image whose `fileId` is anything else, or names nothing, is neither drawn nor saved;
  - its help (`?`), its command palette (⌘/, Ctrl+/, ⌘⇧P), save, open and export (⌘S, ⌘O, Ctrl+⇧E) are refused, as is its context menu, whose items include a link; in a text being written, only save, open and export are refused;
  - a drop is taken only when it holds only PNG and JPEG files; a paste reaches Excalidraw, whose images go through the upload below, but Excalidraw's own clipboard, which carries its images' bytes past that upload, is refused and said;
  - Excalidraw listens for its command palette on the window, ahead of the page's handlers. 0.18.1 mounts it only for a host that renders `<CommandPalette />`, which the canvas doesn't, but the canvas's guard listens on the window too, set in a layout effect so it runs first;
- **An image put on the canvas is uploaded before it is drawn.** `generateIdForFile`, which Excalidraw calls before it decodes or shrinks anything, checks its type (PNG or JPEG), its size (2 MiB), and its pixels as its header says (8,192 a side, 4,096 × 4,096 in all, as artifactr ADR-0092's limits), uploads it as the person, and names it by the digest the server answers with. A refusal is said on the canvas, and nothing is put on it.
- **pica and image-blob-reduce are stood in for** by a few lines that shrink an image on a canvas of the page (`createImageBitmap`, `drawImage`, `toBlob`), loaded by the add-on as their modules (`app/excalidraw.ts`). No WebAssembly, no worker, no `require`.
- **The policy is unchanged: no `img-src blob:`.** Excalidraw draws an image from a `data:` URL, which the policy already allows, and the stand-ins make no `blob:` URL. The CSP harness pastes and draws an image under the policy with no violation, so the RFC's `img-src blob:` isn't needed, and isn't added.

### Saving

- **An edit is the patch every writer sends.** `app/src/on-demand/patch.ts` ports `element_patch` and `rebase` to TypeScript. `packages/artifactr/schemas/excalidraw_patches.json`, written by artifactr's tests (`tests/excalidraw/patch_cases.py`), holds the patch for each case (nothing changed, moved and added, deleted with its label, a label edited, an image put on with its file, an element the edit leaves out) and the rebase for each (kept, won above the head with a new nonce, the lower nonce of one version, the head's taken). Both sides check it.
- **An edit is of what the canvas drew.** The base is the scene as Excalidraw restored it when the person pressed Edit, at the version the canvas opened on (the page may read a newer one while it is open, which the scene doesn't hold), so an element they didn't touch isn't sent, and a peer's save meanwhile is a conflict, not overwritten.
- **The cadence:** an edit is sent when the person lets go of what they drew, or after two seconds of quiet; at most once every five seconds; one at a time (artifactr ADR-0088's cadence).
- **It is sent on the workspace's stream as the person's own `edit_artifact`,** with a summary such as "2 elements changed on the canvas, 1 image added". The revision is theirs, as any command they send is: their actor, on the log and in the revisions.
- **What it comes to:**
  - applied, the version saved on moves on, and the canvas says "Saved";
  - a version conflict, someone having saved meanwhile: the head is read again, the person's changes are moved onto it as Excalidraw reconciles (`rebase`: the higher version wins, then the lower nonce), and sent once more; a second conflict stops saving and says so. What is drawn of the head is taken as the canvas takes any diagram, so a peer's or an agent's link, embedded page, image it has no bytes for, or number out of reach never reaches the scene; and what is sent is what was drawn, even as the canvas closes. The head's images, a peer's or an agent's, are drawn too, their bytes read as any diagram's;
  - proposed, where a policy routes the person's edit to review: saving stops, and the canvas says it was proposed;
  - refused: saving stops, and the canvas says why, in the kit's words for the rejection's type ([ADR-0070](0070-a-servers-words-never-reach-a-reader.md)), never the server's message.
- **Closing sends what isn't saved yet,** whatever the cadence, from the scene as it was just before Excalidraw let it go. An image still being put on the canvas as it closes isn't on the scene yet, and isn't saved.
- **A diagram past its limits isn't sent.** 2,000 elements, tombstones included, and 1 MiB (artifactr ADR-0086): the canvas stops saving and says so; the server refuses it too.

### Where it lives

- **All of it is in the `canvas` add-on**, `app/src/on-demand/`: `canvas.tsx`, `canvas-host.ts`, `patch.ts` and `saver.ts`.
- **The client's image functions are a module of their own,** `@portalr/client/diagrams`, which only the add-on imports, so the client's chunk in the first load doesn't grow.
- **The page gives the canvas where it is, and as whom,** through what it already gives its apps: `AppHost.place`: artifactr's and grantr's surfaces, the person signed in, the tenant and the workspace. The card passes it, and the artifact it shows, to the canvas. A page that gives no place, or shows no artifact, gets the canvas to look at. The CSP harness gives a host of its own through `CanvasHostContext`.
- **Sizes, measured on this branch against `origin/main`:**

  | | main | here | ceiling |
  |---|---|---|---|
  | app initial | 202,761 | 202,774 | 203,000 |
  | `canvas` total | 328,803 | 333,974 | 350,000 |
  | `canvas` largest | 158,997 | 163,661 | 165,000 |

  The ceilings are unchanged. ADR-0088's `canvas-images` add-on isn't made: editing and the images' code are about 5.2 kB together, and an add-on of its own would cost more in requests than it saves.

## Consequences

- People draw on diagrams and put PNG and JPEG images on them, each save a revision of theirs, held by the checks the agent's are.
- The canvas reconciles with a head that moved on, but doesn't show others' changes while it is open; presence and live updates are collaboration's (PR 4).
- A revision is a save, every five seconds at most while someone draws; artifactr ADR-0091's thinning is for that.

## Alternatives considered

### For images

- **Un-stub pica and image-blob-reduce:** rejected. The bundler's `require` helper would join the first load, pica's worker needs `blob:` in `worker-src` and its WebAssembly `'wasm-unsafe-eval'`.
- **Upload the image as Excalidraw's file data, a `data:` URL, in the scene:** rejected in artifactr ADR-0092.

### For the patch

- **Send the whole scene, `replace /elements`:** rejected. Every save would replace every element, the checks couldn't tell a person's edit from a removal, and two people's saves would undo each other's.
- **A patch library's diff:** rejected. It would write `remove`s and nested paths, which the checks refuse, and not the shape the agent's tools send.

### For the host

- **The canvas reads the route's context through the router's hooks:** rejected. Reaching the router's modules from the add-on split them into more chunks of the first load, about 400 bytes measured.

## Action items

1. [x] artifactr's image routes, their document and their tests (artifactr ADR-0092).
2. [x] The patch builder and rebase, held to artifactr's by a shared fixture.
3. [x] Edit mode, its guards, the saver, and the stand-ins for pica and image-blob-reduce.
4. [x] The CSP harness's editing test, and the scenario.
5. [ ] Collaboration (PR 4): presence, others' changes while the canvas is open.
