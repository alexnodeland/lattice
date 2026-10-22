# ADR-0086: Diagrams' data: an element-scoped patch and its checks

**Status:** Proposed
**Date:** 2026-10-22
**Deciders:** Alex Nodeland
**Implements:** the data slice of [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 2 (O1, O6), as [lattice ADR-0026](../../adr/0026-a-distribution-needs-a-reason-integrations-are-extras.md) amends its packaging

## Context

RFC-0006 makes an Excalidraw diagram an ordinary JSON artifact, edited by JSON Patch scoped to its elements. Its phase 1, the shared gate, is built ([ADR-0081](0081-a-gate-before-access-integrations-switched-off-answer-not-enabled.md), lattice ADR-0027). Phase 2 is the type, the patch builder, the checks, the agent's toolset, the worker and images in `Blobs`. This record covers the part with no worker and no UI: what a diagram is, how an edit is built and rebased, and what the server refuses.

## Decision

- **An extra, `artifactr-ai[excalidraw]`, imported as `artifactr.excalidraw`.** It is a plugin nothing else in artifactr imports, built on core's and the workspace's public API and on Pydantic alone (`tests/test_layering.py`). Its data layer needs no dependency beyond artifactr's own, so the extra is empty for now; the worker's client joins it.
- **`Diagram`, kind `excalidraw_diagram`, `write_policy = "propose"`.** Its data:
  - `name`;
  - `elements`, keyed by each element's id;
  - `files`, keyed by each image's digest;
  - `scene`, what every viewer shares.

  An `Element` validates only `id`, `type`, `version`, `versionNonce`, `isDeleted`, `index` and `updated`, and keeps every other field as written, under Excalidraw's own camel-case names.

  - `version` and `updated` are strict integers up to 2^53 − 1, the largest JavaScript holds exactly. `versionNonce` is a strict integer from 0 to 2^31 − 1. No bool or float is coerced.
  - A field that holds NaN or an infinity is refused, since JSON would store it as null. So is one nested past what JSON encodes.
  - `type` is open on purpose: a type a newer Excalidraw writes is kept, not refused. An image is a `DiagramFile` with `Blob`'s shape (`sha256`, `size`, `media_type`). It is kept apart from `Blob` so the data layer doesn't import the `files` extra; images through `Blobs` come with the worker.
- **The type refuses** an element kept under another's id, an image kept under another's digest, more than 2,000 elements (tombstones included), and more than 1 MiB of JSON. The owner set these limits from phase 0's measurements. Every commit validates and stores the whole document, so its cost grows linearly with the scene. Each edit was one element's `test` and `replace`:

  | Elements | JSON | Edit in memory (median / max) | Edit on SQLite (median / max) | Storage a revision |
  |---|---|---|---|---|
  | 26 | 0.02 MB | 0.7 / 1 ms | 5.6 / 10 ms | 24 kB |
  | 1,334 | 0.76 MB | 30 / 72 ms | 67 / 135 ms | 899 kB |
  | 6,667 | 3.80 MB | 190 / 297 ms | 391 / 441 ms | 4.5 MB |
  | 26,667 | 15.2 MB | 967 / 1,787 ms | 2,317 / 3,513 ms | 18 MB |

  At the limits, an edit takes about 40 ms in memory or 90 ms on SQLite, for a revision of about 1.2 MB. The RFC's 5,000 elements would be about 2.9 MB and 200 to 400 ms a commit. PostgreSQL wasn't measured.

- **The patch builder, `element_patch(base, elements, files)`:**
  - a changed element is `test` of its base version, then `replace`;
  - a new element is `add`;
  - a dropped element is `test`, then `remove`;
  - a new image is `add`.

  `rebase(base, local, head)` moves a writer's elements onto a newer head after a `version_conflict`. It reconciles the way Excalidraw 0.18.1's `reconcileElements` does: the higher version wins, and at one version the lower nonce. Where the writer's element wins, it is resent above the head's version with a new nonce. `reconcile` and `won` are the same rule, for a writer that merges.

- **The checks, `excalidraw_checks()`**, run on every surface, for an edit, a proposed edit, and a proposal accepted against the head:
  - an element an edit changes must grow its `version` past the head's;
  - an `add` of an id the head already has is refused;
  - an image is added only, never replaced or removed. This is checked on the result, not on the patch's paths, so removing or replacing `/files`, a root replace, and a `move` or `copy` are all held to it.

  The result is loaded as core loads it, so data the type refuses is refused here as core would refuse it.

- **`render_for_agent`** describes a diagram in at most 4,000 characters: frames, shapes with their labels, arrows as `A --label--> B`, free text, counts and the bounding box. It reads live elements only, does no IO, and stores nothing. What the agent reads is written by people, so:
  - every word from the diagram is quoted on one line, its quotes escaped, at most 80 characters;
  - an arrow names a bound element only if it is a live element's id, and is "(free)" otherwise.
- **The wire schema** is checked in at `schemas/artifactr_excalidraw.v1.json`, drift-tested, and generated into portalr's client types.
- **`excalidraw` is off by default** in lattice-core's registry, as lattice ADR-0027's amendment records.

## Consequences

- Easier: two proposals on different elements both accept. A proposal whose element moved since fails whole, as `patch_failed`. A stale direct edit conflicts, and rebases cheaply because ids are stable. RFC-0006's exit criteria for this slice are tests, on every storage and over REST.
- Easier: an application registers `EXCALIDRAW_TYPES` and `excalidraw_checks()` and gates them with `excalidraw_key_of`, as it does forms.
- Harder: an application with checks of its own for the same command types composes them, since `Workspaces(checks=...)` takes one check a command type.
- A known gap: an element patched out with a bare `remove`, with no `test`, is deleted at once rather than left as a tombstone. RFC-0006 keeps tombstones a day, so a client mid-edit doesn't bring the element back. The canvas only ever writes `isDeleted`, and the tombstone sweep (U3) is what removes them. Refusing a `remove` that isn't the sweep's comes with the sweep.
- Not yet: the agent's `DiagramTools`, the worker (Mermaid and skeleton conversion, rendering), images in `Blobs`, the tombstone sweep (U3), and the canvas (phase 3).
