# ADR-0091: Diagrams' tombstones swept, and their revisions thinned

**Status:** Proposed
**Date:** 2026-10-23
**Deciders:** Alex Nodeland
**Implements:** [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s U3, and the retention rule [ADR-0088](0088-excalidraws-phase-0-what-the-canvas-costs-and-needs.md) left to a record of its own, both as the owner ratified them on 2026-10-23

## Context

A deleted element stays as a tombstone (`isDeleted`), so that a client mid-edit doesn't bring it back. ADR-0086's checks refuse removing an element by any edit. With a hard limit of 2,000 elements, tombstones included, a diagram at its limit can't shrink until something removes old tombstones.

Phase 0 also measured revision growth: every revision stores the whole scene, about 29 MB a person-hour at a 30 KB scene under the five-second cadence, and more for larger scenes.

## Decision

- **The sweep, `sweep_tombstones(ws, now=...)`, removes a tombstone 24 hours after the revision that made it.**
  - It runs as the application's own actor, `SWEEPER` (`system:excalidraw-sweep`). It needs a handle that sees every artifact.
  - The age is the server's: the time of the first revision in which the element had the tombstone's version. A revision saved before artifactr stamped a time counts as old. The element's own `updated`, which a client writes, is never used.
  - It makes one revision a diagram, each removal tested against the tombstone's version. A diagram changed meanwhile is skipped, for the next sweep.
  - An archived diagram keeps its tombstones.
  - The application runs it on a schedule of its own, as it runs native files' collection.
- **Only the sweep removes.** ADR-0086's checks let the actor `SWEEPER` remove an element that is a tombstone in the head, and nothing else. Every other remove, including a remove of a live element by the sweep, is still refused.
- **Retention, as ratified:**
  - after 24 hours, a diagram's revisions are thinned to one an actor every ten minutes;
  - the revisions that pending proposals are based on are kept;
  - tombstones are removed after 24 hours by the sweep above.

  The thinning is a later change (RFC-0006's phase 4), once the canvas makes real volume. This records the rule it keeps to.

## Consequences

- Easier: a diagram at its limit can shrink again a day after its elements are deleted, and a client that held a deleted element for a day has long since reconciled it.
- Harder: an application runs one more scheduled job, beside native files' collection.
- Until the thinning lands, a diagram's revisions grow with its edits, as every artifact's do.
