# ADR-0018: A page takes one of the tenant's readings, is kept, and is paced

**Status:** Accepted
**Date:** 2026-10-22
**Deciders:** Alex Nodeland
**Amends:** [ADR-0017](0017-a-persons-upload-told-by-its-bytes-read-before-it-is-committed.md)

## Context

A security review found that the page routes starved the worker. The worker runs one call at a time, and a call that waits past its 30-second deadline for its turn fails with `timeout` ([ADR-0013](0013-the-worker-runs-each-call-under-limits-behind-a-token.md)). ADR-0017 held uploads and check-ins to a pace, a share of places, and the tenant's readings. A page took none of these:

- `GET .../versions/{v}/pages/{p}` and a proposal's page skipped the routes' pace and places.
- `NativeFiles.render` and `render_proposed` took no reading.
- No page was kept.

So a viewer looping on one page of a heavy file, a few requests at once, filled the worker's queue. Every tenant's uploads, check-ins and agents' edits then failed `timeout`, 503.

The review also found that an upload given the id of a file hidden from its uploader was sniffed, read by the worker and stored before its commit refused it.

## Decision

- **A page the app renders takes one of the tenant's readings** (`readings`, two by default), as a file the app reads does. Past them it is refused at once with `Busy`, 429. One tenant's calls, of any kind, never queue more than its readings ahead of another tenant's.
- **A rendered page is kept** by `NativeFiles`, in this process, keyed by its app, the SHA-256 of the bytes it is of, the page and the scale, up to `pages` bytes (64 MiB by default), the least lately read let go first. The same page asked for again reaches neither the app nor any reading. It is given only after the workspace has resolved the file for its reader, so it is the page of bytes they may read.
- **Each person's pages that reach the app are paced:** `files_router`'s `renders_per_minute`, 30 by default, past which one is refused with 429, `rate_limited`. A page that is kept counts against no pace.
- **The response tells a browser to keep it:** `Cache-Control: private, max-age=86400`, since a version's page and a proposal's never change, with an `ETag` of its bytes. A request whose `If-None-Match` names it is answered 304.
- **An upload to an id hidden from its uploader is refused first,** as its commit would refuse it, as a missing artifact, before its bytes are sniffed, read or stored.

## Options considered

### A pool of the worker's turns, fair across tenants

**Cons:** the queue is the worker's own, behind a token, in another process. Fairness there would need tenants on the wire. The readings are already per tenant in the application, which is where the calls come from.

### Pages cached in the blob store

**Cons:** a page would be bytes stored and counted against a quota, and collected. Kept in memory and bounded, a page costs nothing past a restart but its first render again.

## Trade-off analysis

Taking a reading costs a tenant two calls at once, of any kind. It buys a bound that holds whatever the routes do. Keeping pages costs memory, bounded. The pace costs a page past it 429, which a viewer's next scroll retries.

## Consequences

- Easier: a page read again is free, in the application and in the browser. One tenant's viewers can't time out another tenant's work.
- Harder: a tenant whose two readings are rendering gets `Busy` for an upload until one ends, as it would for two uploads.
- To revisit: a lock shared between an application's replicas, which count their own readings.

## Action items

1. [x] `render` and `render_proposed` in a reading, and their pages kept (`pages`).
2. [x] `renders_per_minute`, `Cache-Control` and `ETag` on the page routes.
3. [x] An upload to a hidden id refused before it is read.
