# ADR-0092: A diagram's images, uploaded by a person and read where it names them

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland
**Implements:** [lattice RFC-0006](../../rfcs/0006-excalidraw-diagrams-drawn-live.md)'s phase 3b, artifactr's half: the route a pasted image is uploaded to

## Context

- **A diagram names its images by digest.** `Diagram.files` maps a SHA-256 to a `DiagramFile` (its size and type), and an `image` element's `fileId` is that digest ([ADR-0086](0086-diagrams-data-an-element-scoped-patch-and-its-checks.md)). The bytes are kept in the native files' blob store, whose collection keeps what any revision names (`NativeFiles(naming=(Diagram,))`).
- **The agent puts no image on a diagram.** Until now nothing wrote those bytes: a person's canvas had nowhere to send an image they paste or choose.
- **An image is the one element whose bytes are fetched.** A diagram is anyone's in the workspace to write, so an image route must not become a way to serve script, reach another origin, or read another tenant's bytes.
- **An SVG can run script and fetch.** Excalidraw takes SVG images; the RFC ruled them out.

## Decision

- **`artifactr.excalidraw.fastapi.diagrams_router(workspaces, blobs, *, resolve_actor, integrations=None, uploads_per_minute=30)`** is mounted beside `artifactr_router`, with the same workspaces and actor resolver, and the native files' blob store. It has two routes.
- **`POST /workspaces/{w}/diagrams/{id}/images` uploads one image, as the person:**
  - the diagram must exist in that workspace, and the person must be allowed `artifactr:edit_artifact` on it; diagrams switched off for the workspace answer `409 not_enabled`;
  - its `Content-Type` is `image/png` or `image/jpeg`, else `415 unsupported`; SVG and every other type are refused;
  - it is at most `MAX_IMAGE`, 2 MiB: a `Content-Length` past it is refused before the body is read, and a body that grows past it is refused as it is read, `413 too_large`;
  - its first bytes must be a PNG's or a JPEG's signature, the type it says it is, and its header must give its size, a PNG's `IHDR` or a JPEG's first start-of-frame, else `422 not_an_image`: a polyglot, a PNG's signature then an SVG, is refused so;
  - its size, as that header says, is at most `MAX_SIDE`, 8,192 pixels a side, and `MAX_PIXELS`, 4,096 × 4,096 (16,777,216) in all, else `413 too_many_pixels`, and neither side 0, else `422 not_an_image`: a few kilobytes can say 20,000 × 20,000, which every viewer would decode into gigabytes;
  - each person is paced per tenant (`uploads_per_minute`, 30 by default), `429 rate_limited` with `Retry-After`. The pace is each process's own, as native files' is: with N replicas a person may upload up to N × 30 images a minute, at most N × 60 MiB;
  - the store's limit and quotas answer `413`, `over_quota` for a quota;
  - it answers `201` with the `DiagramFile` the canvas names it by: `{sha256, size, media_type}`.
- **The upload changes no diagram.** The person's next edit names the image, adding `/files/{sha256}` and its element in one patch, as an agent's would. Until then the bytes are unnamed. The native files' collection (`NativeFiles.collect`, told of diagrams by `naming=(Diagram,)`) removes them once they are older than its `keep`, a day by default; it runs only where an application runs native files' collection, so elsewhere unnamed images stay until it does. A `files` entry is not checked against the store when an edit names it: the read below serves only bytes that are an image.
- **`GET .../images/{sha256}` reads an image only where the diagram names it.** A digest the diagram's head doesn't name is `404 not_found`, and so is one it names whose bytes this diagram never had, so a digest known from another workspace, tenant or diagram reads nothing, even where another diagram names it too. A hidden diagram answers as a missing one. The diagram is read through the workspace as the person, as any read of it is, and its images stay readable while diagrams are switched off. It is served as the type its own bytes say, PNG or JPEG, whatever the diagram says; bytes that are neither are `404`. It is served with `X-Content-Type-Options: nosniff`, `Content-Security-Policy: sandbox` and `Cache-Control: private, max-age=86400, immutable`.
- **Tenants are kept apart by the blob store's scope**, `(tenant, workspace)`, as native files are, and by the workspace's own access check.
- **Its OpenAPI document is committed**, `schemas/artifactr-excalidraw.openapi.json`, and portalr's client is generated from it.

## Consequences

- A person can put a PNG or a JPEG on a diagram, and nothing else; the agent's tools are unchanged.
- An image's bytes cost the workspace's quota from upload, and are freed by the collection if no edit names them.
- The excalidraw layer now imports `artifactr.fastapi`, the files' pacing, `fastapi` and `starlette`, as its tests of layering record.

## Alternatives considered

- **Images as `data:` URLs inside the scene:** rejected. A 2 MiB image would be most of a diagram's 1 MiB limit, and every revision would copy it.
- **The native files' upload route:** rejected. It makes a native file, an artifact of its own, with its own type and check-in; an image is part of one diagram.
- **SVG, sanitised:** rejected, as the RFC decided. A sanitiser is one more thing to get right, and the canvas has no need of vectors from outside.
