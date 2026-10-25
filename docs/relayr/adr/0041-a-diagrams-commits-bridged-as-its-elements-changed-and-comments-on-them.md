# ADR-0041: A diagram's commits bridged as its elements changed, and comments on them

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland

Records [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 4, "events and feedback": `excalidraw:elements_changed`, and feedback anchored by element.

## Context

- **A diagram's commit is an `artifact_changed`**, and its patch is element-scoped ([artifactr ADR-0086](../../artifactr/adr/0086-diagrams-data-an-element-scoped-patch-and-its-checks.md)). Bridged as the default set's `artifactr:artifact_changed`, it carries the patch, and a rule would read JSON Patch to learn which shapes changed.
- **A canvas saves every few seconds** while a person draws, so a rule needs one event per commit, saying which elements it touched.
- **The RFC wants comments as feedback** on an artifact version, anchored by an element id, so a rule can "propose a fix for the commented shape". No comment is ever drawn as an element.

## Decision

- **`relayr.excalidraw`, behind the `excalidraw` extra** (`artifactr-ai[excalidraw]`), is laid out as `relayr.ui` is (ADR-0038). It has:
  - `EXCALIDRAW_EVENTS` and `EXCALIDRAW_PUBLISHERS`, for reflexr;
  - `EXCALIDRAW_PROJECTIONS`, for the follower's `Projections`.
- Only this module imports `artifactr.excalidraw`, which the layering test holds.
- **`excalidraw:elements_changed`** is bridged once per commit to a diagram: a person's save, an accepted proposal, or the sweep. It carries:
  - the author, the thread and the turn;
  - the diagram's id and version, the commit's summary, and the proposal whose acceptance made it, if one did (`proposal_id`);
  - the elements it `added`, `changed` and `removed`, each an id with its label where the commit says one. A text's label is its own text; a container's comes from the text bound in it, in the same commit, over any name of its own; any other's is its name. Each label is at most `MAX_LABEL`, 200 characters, cut with an ellipsis. An element is named once, by the last op on it.
- **What counts as what:**
  - An element marked deleted (a `replace` with `isDeleted`) is removed, as the canvas shows it, and so is the sweep's `remove` of a tombstone.
  - A version's `test` and an image's `/files/...` are passed over.
  - A diagram's creation is one event, its live elements added.
  - A commit that touches no element, such as an image's file alone, bridges nothing: rules on a diagram are rules on its elements.
  - Its archiving, and a patch that isn't element-scoped (a rename's text edits), are bridged as the default set's.
- **`excalidraw:` is reserved to the follower's publisher**, as `ui:` is, so no client publishes a diagram's changes itself ([reflexr ADR-0057](../../reflexr/adr/0057-reserved-publishers.md)).
- **A comment on an element is feedback**: artifactr's `DiagramComment` (`diagram_comment`). It targets an artifact version, with `element_id` and `text`.
  - The diagrams' checks refuse it, as `validation_failed` at `value.element_id`, where that version doesn't hold the element live. A version thinned away (artifactr ADR-0094) is read as the head.
  - A comment keeps its version after that revision is thinned away, and its element may since have gone from the head. It stays anchored to the version it was given on; a rule that proposes a fix reads the head.
  - It is bridged as the default set's `artifactr:feedback_given`, with `element_id` in its value. A rule finds the shape there and may propose a fix for it, as an ordinary agent run does.
- **stackr's template** adds the extra, the events, the publishers and the projection when it has diagrams and the bridge, merged with the forms' projections where it has those too.

## Consequences

- A rule on a diagram fires once per commit, and knows which shapes changed without reading a patch. One on a comment knows which shape it is about.
- A diagram's commit with an element-scoped patch is no longer bridged as `artifactr:artifact_changed`; a rename's text edits still are. A rule written on it for a diagram's elements moves to `excalidraw:elements_changed`. The extra is unreleased, so no application needs a migration.
- **An element's text leaves the diagram** into events: reflexr's log, the values rules see, and whatever their runs send on, such as webhooks and run logs. Each label is bounded at 200 characters, but what a person wrote on the canvas is in those places as far as it goes.
- **Commenting from the canvas**, a person picking a shape and writing, isn't built here. It is portalr's, and costs code in the canvas add-on. A comment is given today through the feedback command, as any feedback is, and an agent or a client can give one.

## Alternatives considered

- **Leave diagrams to `artifactr:artifact_changed`:** rejected. Every rule would parse JSON Patch, and a removal looks like a replace.
- **A comment as an element on the canvas:** rejected by the RFC. It would be drawn, saved and counted as part of the diagram.
