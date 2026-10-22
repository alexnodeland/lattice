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

  An `Element` validates only `id`, `type`, `version`, `versionNonce`, `isDeleted`, `index` and `updated`, and keeps every other field as written, under Excalidraw's own camel-case names. An image is a `DiagramFile` with `Blob`'s shape (`sha256`, `size`, `media_type`). It is kept apart from `Blob` so the data layer doesn't import the `files` extra; images through `Blobs` come with the worker.
- **The type refuses** an element kept under another's id, an image kept under another's digest, more than 5,000 elements, and more than 1 MiB of JSON. Those two limits are RFC-0006's placeholders, awaiting phase 0's measurements.
- **The patch builder, `element_patch(base, elements, files)`:**
  - a changed element is `test` of its base version, then `replace`;
  - a new element is `add`;
  - a dropped element is `test`, then `remove`;
  - a new image is `add`.

  `rebase(base, local, head)` moves a writer's elements onto a newer head after a `version_conflict`. It reconciles the way Excalidraw 0.18.1's `reconcileElements` does: the higher version wins, and at one version the lower nonce. Where the writer's element wins, it is resent above the head's version with a new nonce. `reconcile` and `won` are the same rule, for a writer that merges.
- **The checks, `excalidraw_checks()`**, run on every surface, for an edit, a proposed edit, and a proposal accepted against the head:
  - an element an edit changes must grow its `version` past the head's;
  - an `add` of an id the head already has is refused;
  - an image is added only, never replaced or removed.

  The result is loaded as core loads it, so data the type refuses is refused here as core would refuse it.
- **`render_for_agent`** describes a diagram in at most 4,000 characters: frames, shapes with their labels, arrows as `A --label--> B`, free text, counts and the bounding box. It reads live elements only, does no IO, and stores nothing.
- **The wire schema** is checked in at `schemas/artifactr_excalidraw.v1.json`, drift-tested, and generated into portalr's client types.
- **`excalidraw` is off by default** in lattice-core's registry, as lattice ADR-0027's amendment records.

## Consequences

- Easier: two proposals on different elements both accept. A proposal whose element moved since fails whole, as `patch_failed`. A stale direct edit conflicts, and rebases cheaply because ids are stable. RFC-0006's exit criteria for this slice are tests, on every storage and over REST.
- Easier: an application registers `EXCALIDRAW_TYPES` and `excalidraw_checks()` and gates them with `excalidraw_key_of`, as it does forms.
- Harder: an application with checks of its own for the same command types composes them, since `Workspaces(checks=...)` takes one check a command type.
- Not yet: the agent's `DiagramTools`, the worker (Mermaid and skeleton conversion, rendering), images in `Blobs`, the tombstone sweep (U3), and the canvas (phase 3).
