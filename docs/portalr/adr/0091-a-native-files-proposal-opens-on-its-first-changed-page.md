# ADR-0091: A native file's proposal opens on its first changed page

**Status:** Accepted
**Date:** 2026-10-28
**Deciders:** Alex Nodeland
**Amends:** [ADR-0089](0089-a-native-files-proposal-says-what-it-does-in-its-thread.md) (what an open proposal's card shows before it is asked)

## Context

[ADR-0089](0089-a-native-files-proposal-says-what-it-does-in-its-thread.md) said what a native file's proposal does, in words, and kept Compare closed until asked. A reviewer still had to open it to see a picture of the change, and on a phone the sheet showed no picture at all (issue 1090). A page that couldn't be drawn said only "This page couldn't be shown.", whether the app was busy, the proposal's bytes were missing, or its app draws no pages.

## Decision

- **Each change names the pages it changes, where its craft can say** (`pages` on each item, [native files ADR-0020](../../artifactr/files/adr/0020-a-proposal-said-in-words-and-previewed-by-its-own-pages.md)). DeckCraft names the slides a batch adds, numbered as they end; WordCraft only the page a header or footer command names, since its words flow. Any other craft names none.
- **Every craft the template wires says its commands in its own verbs** (native files ADR-0020's tables, now for GridCraft, PdfCraft, CADCraft, PhotoCraft, VectorCraft, DesignCraft, FigCraft, FilmCraft, EffectCraft, SoundCraft, FreeCAD and Blender), each read from its pinned release's catalogue, or for FreeCAD and Blender from the adapter's script's steps. A test fails when the template wires a craft that has no table and isn't in `GENERIC` (LightCraft alone, which keeps no native file).
- **On a desktop, Compare is open at first, on the first changed page alone:** the least page a change names, or else the first page whose picture differs from the head's, read a page at a time, at most four. "Compare more pages" shows them from the first, as before.
- **On a phone, the sheet shows that page under "Before and after"**, below the changes; Compare stays closed.
- **A page that isn't drawn says why, in the card's words, never the server's:**
  - busy, paced or too slow (429, 503): "Still preparing the picture. Try again in N seconds.", N being the server's `Retry-After`, or 10, with Try again; a page's picture isn't asked again on its own;
  - the proposal's bytes not stored (409, `reason: content_unavailable`): "The proposed file isn't stored.";
  - any other: "This page couldn't be shown.", with Try again.
- **An app that draws no pages** (GridCraft and SoundCraft) says "<App> can't show a picture of this change. Its words and commands are listed above." and reads none.
- **While pictures are read, a polite status line says so:** "Preparing the pictures of its pages…".

## Options considered

### Option A: The first changed page, open on a desktop (chosen)

**Pros:** A reviewer sees the change before deciding, at the cost of one or two pages read per card.
**Cons:** A card drawn on a desktop reads its words and a page or two as it is drawn.

### Option B: Every page open at first

**Cons:** Four pictures, each a reading of the tenant's, for every proposal on the page.

## Consequences

- `PageShown`'s failed state carries what it says and a retry.
- `ContentUnavailable` says `reason` and `part` in its refusal, so a client tells it from another conflict.
