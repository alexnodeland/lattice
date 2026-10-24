# ADR-0078: The others on a diagram's canvas, and their revisions as they arrive

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland

This records portalr's half of [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s live collaboration. It builds on [ADR-0074](0074-editing-a-diagram-on-its-canvas-and-the-images-put-on-it.md)'s editing and on the frames of [artifactr ADR-0093](../../artifactr/adr/0093-presence-who-has-an-artifact-open-passed-on-and-never-stored.md).

## Context

- **A canvas saved alone.** It didn't show who else had the diagram open, and it didn't draw what they saved while it was open. It only met their revisions as conflicts.
- **The first load has no room.** The app's initial was 202,834 bytes of its 203,000 once session replay (#718) landed.
- **A peer's elements are anyone's to write**, like a diagram's own (ADR-0072, ADR-0074).

## Decision

### Presence

- **The canvas has a connection of its own** to the workspace's stream (`on-demand/presence.ts`).
  - It says `hello` from the head of the log asking for no events (`events: false`), so it carries none, and it watches the one diagram. Its own `peer_left` tells it its watch ended.
  - The page's own stream carries no presence, and its code holds none. The canvas loads it, and opens and closes it with itself. On a drop it connects again and watches again.
  - The price is one more connection per open canvas, for as long as it is open.
- **What it says:**
  - The pointer, and what is selected.
  - While the person draws with the pointer down, what they are drawing and moving. A viewer says nothing of that, and the server would drop it.
  - At most twenty frames a second, and at least one every five, so the others don't count it as gone. It also speaks once as it opens.
  - A frame past 60 KiB leaves out what is changing.
- **What it shows:**
  - Each peer is one of Excalidraw's collaborators, by the name the server stamped and a colour, its pointer and its selection. No avatar URL is ever set. The colour is one of the kit's chart colours, as the browser resolves them in the scheme and colour-blind mode (`data-cvd`), since Excalidraw's canvas takes no custom property; peers take them in the order they were first heard. The name, beside the pointer and in "Here now", is what tells peers apart.
  - A list, "Here now", names who is there, for everyone and for assistive technology. Excalidraw's own avatars, which would sit over it, are hidden. Who came and who left is said in a polite live region, gathered and said at most every two seconds. It is a live region, not a second `status`: the canvas's status says how saving goes.
  - What a peer is drawing is a picture over the canvas, drawn again only as its elements' versions change, and with nothing past 100,000 from the origin or 20,000 a side (`on-demand/pictures/ghosts.tsx`): Excalidraw's own SVG export of their elements, faint and labelled with their name. It is never in the scene, so nothing of it is saved as this person's.
  - A peer's elements are taken first as the canvas takes any diagram's: no link, no embedded page, no image, nothing out of reach. Because the picture is an SVG, whose colours are attributes, only plain colours reach it (a hex, `transparent`, or `rgb()` or `hsl()` of numbers), so a `url(...)` never does; a colour longer than 64 characters isn't read at all, and the pattern reads each run of spaces one way, so no colour a peer sends can make it read for long. Strokes are capped at 50, type at 400, and a line at 1,000 points.
  - The export is asked not to inline faces, and still writes a `<style>`, which the policy refuses (the CSP harness shows it), so that is removed. The canvas has its faces already.
  - The picture's code, with Excalidraw's export, is a chunk of its own, fetched only once someone draws.
  - A peer's last picture stays until a revision newer than the one it was drawn on arrives.

### Revisions as they arrive

- **A revision someone else saved is merged as it arrives.** The page already reads each revision again.
  - When the version shown is newer than the one drawn and isn't this person's own save read back, the canvas merges the elements, taken as any diagram's.
  - It merges them with Excalidraw's `reconcileElements` and draws them with `CaptureUpdateAction.NEVER`, so they never enter the person's undo.
  - Their images are read too.
- **The next save is an edit of that revision** (`Saver.merged`). An element Excalidraw had to give an order to as it drew it is sent again, tested at the head's version, which it still is.
- **A save that meets a conflict** is moved onto the head and sent again three times at most, as the RFC says. After that it is kept, still said as "Saving…", and sent when the next revision arrives.

### Size

Everything is in the `canvas` add-on, except what the page needs to type and pass the new frames:

- `AppHost.place.signed` now types `streamSession`, which costs nothing;
- the stream's frame classification now treats every frame but its own as another's. This is 6 bytes smaller than before, and an older app passes over a newer server's frames.

The first load still measures 13 bytes more than main's: a few bytes in each route's chunk, from the names the bundler gives the chunks they import, not from code of this change's. That leaves 153 bytes under the ceiling.

| | main (`8d0c449c`) | here | ceiling |
|---|---|---|---|
| app initial | 202,834 | 202,847 | 203,000 |
| `canvas` total | 333,974 | 338,086 | 350,000 |
| `canvas` largest | 163,661 | 157,599 | 165,000 |

No ceiling is raised. The picture's code, with Excalidraw's SVG export it reaches, is a chunk of its own in the add-on, fetched only once a peer draws, so the add-on's largest chunk is smaller than before.

## Consequences

- People see each other on a diagram, and each other's work as it is saved, without closing it.
- An agent isn't shown as a peer yet. Its `Draft` frames as a ghost are RFC-0006's part 4, still to do.
- The overlay's text uses the page's faces, not the embedded ones, since the policy refuses an inline `<style>`.

## Alternatives considered

- **Presence through the page's stream:** rejected. It needs a listener and a raw send in the client's `Stream`, which the first load carries, for frames only a canvas wants.
- **Peers' elements in the scene, locked and left out of saves:** rejected. A peer moving an existing element would replace the person's own copy of it, and leaving it out of saves without losing the person's own changes is fragile.
- **Raising the add-on's largest-chunk ceiling for Excalidraw's export:** rejected; a ceiling isn't raised. The picture's code is split out instead, fetched only once a peer draws.

## Action items

1. [x] The canvas's presence connection, collaborators, "Here now", and the pictures of what others draw.
2. [x] Merging revisions as they arrive, and three moves before an edit waits.
3. [x] The CSP harness's test of a peer, sanitised, and of a merged revision. The scenario of two people on one diagram.
4. [ ] An agent as a peer (RFC-0006, part 4).
