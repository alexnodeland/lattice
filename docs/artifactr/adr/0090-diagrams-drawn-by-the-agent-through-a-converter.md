# ADR-0090: Diagrams drawn by the agent, through a converter

**Status:** Proposed
**Date:** 2026-10-23
**Deciders:** Alex Nodeland
**Implements:** the agent's part of [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 2 (O6, O7), on [ADR-0086](0086-diagrams-data-an-element-scoped-patch-and-its-checks.md)'s data and [ADR-0088](0088-excalidraws-phase-0-what-the-canvas-costs-and-needs.md)'s worker

## Context

ADR-0086 made a diagram an artifact, edited by element-scoped patches. The agent couldn't draw one. RFC-0006 has it write Mermaid or skeletons, which Excalidraw's own `parseMermaidToExcalidraw` and `convertToExcalidrawElements` turn into elements. Those run in a browser, so the conversion runs in a worker: headless Chromium, one job at a time, a 10 s deadline, no way out (ADR-0088). The worker's image is stackr's, in the next phase-2 change; this record is the application's side of it.

## Decision

- **A `Converter` port** with three calls: `mermaid(source)`, `skeletons(skeletons)` and `render(diagram, files, as_=svg|png)`. Each fails only with `ConversionFailed`, whose reason is one of:
  - `invalid`: what the agent sent;
  - `unsupported`: a kind it doesn't draw;
  - `too_large`: past a limit;
  - `timeout`: past the deadline;
  - `crashed`: anything else.
- **`WorkerConverter`** calls the worker over HTTP, as native files' worker client does.
  - It sends a `POST` of JSON with the worker's token, and opens a new connection for each call.
  - The deadline is 10 s, plus a 5 s grace for the worker to say how it failed.
  - Its sizes are checked before anything is sent: 50,000 characters of Mermaid, and 500 skeletons.
  - Whatever the worker replies, other than its own `{reason, message}`, is `crashed`. A message is cut to 500 characters before the model reads it.
- **`FakeConverter`** draws without a worker, for tests and for an application with none: a flowchart's edges as boxes and arrows, and skeletons as their elements. It refuses any other Mermaid as `unsupported`.
- **`diagram_tools(converter, blobs=, view=, integrations=)`**, a pydantic-ai toolset:
  - `read_diagram(id, page)`: the description, the version, and up to 100 live elements a page, each its id, type, label, place, size and bindings;
  - `draw_mermaid` and `draw`: a new diagram, or a drawing beside what an existing one holds, moved to the right of its live elements. An element id the diagram already has is refused;
  - `edit_elements(id, base_version, ops)`, by element id, never raw JSON Patch (ADR-0003): `move`, `resize`, `restyle`, `relabel` (a text, or the label bound in a shape or an arrow), `delete` (the element and its label, as tombstones) and `connect` (an arrow, with a label). A stale `base_version` is sent back to read again;
  - `view_diagram`: a PNG, offered only with `view`, as `view_page` is.
- **How the tools behave.**
  - Each change goes through the workspace and its checks, so the agent's changes are proposals, as a diagram's write policy says.
  - A refusal goes back to the model to fix, up to three tries a tool.
  - The tools are offered only while `excalidraw` is on in the run's workspace, which it isn't by default.
- **Images go to native files' blob store.**
  - A conversion's images, such as a Gantt chart Excalidraw draws only as a picture, are put in the `Blobs` store. Each image element's `fileId` becomes the bytes' digest, which is the image's key in the diagram.
  - Without a store, such a drawing is refused, and the model is told to draw shapes.
  - Native files' collection takes `naming=(Diagram,)`, so it keeps what diagrams name too.
  - So the extra now needs the `files` extra, and is `artifactr-ai[excalidraw]` = `artifactr-ai[files]`.

## Consequences

- Easier: an agent draws and edits diagrams with no browser open, and an application without the worker still runs the toolset on the fake.
- Harder: the extra brings the files extra's dependencies, for the blob store and httpx.
- Not yet: the worker's image (stackr, next), the canvas (phase 3), and the `Draft` frames that show an agent's drawing live (phase 3).
