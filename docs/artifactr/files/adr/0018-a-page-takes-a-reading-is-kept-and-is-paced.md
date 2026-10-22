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

- **A page the app renders takes one of the tenant's readings** (`readings`, two by default), as a file the app reads does. One tenant's calls, of any kind, never queue more than its readings ahead of another tenant's at the worker.
- **A page waits for a reading, up to the app's deadline,** in the application, not at the worker: portalr asks for four pages of a file at once, and a proposal's comparison for eight, so a viewer's own batch is served in turn rather than refused. An upload or a check-in is still refused at once, as ADR-0017 says. A page that waits past the deadline is refused with `Busy`, 429, with `Retry-After`.
- **portalr's client asks again after a 429,** once its `Retry-After` has passed, or after a backoff, up to three times: a 429 is no longer a refusal for what was asked.
- **A rendered page is kept** by `NativeFiles`, in this process, keyed by its app, the SHA-256 of the bytes it is of, the page and the scale, up to `pages` bytes (64 MiB by default), the least lately read let go first. The same page asked for again reaches neither the app nor any reading. It is given only after the workspace has resolved the file for its reader, so it is the page of bytes they may read.
- **Each person's pages that reach the app are paced:** `files_router`'s `renders_per_minute`, 30 by default, past which one is refused with 429, `rate_limited`. A page is counted once it holds a reading, so one refused as busy spends none of the pace, and a page that is kept counts against none.
- **The response tells a browser to keep it:** `Cache-Control: private, max-age=86400`, since a version's page and a proposal's never change, with an `ETag` of its bytes. A request whose `If-None-Match` names it is answered 304. The tag is of the PNG, so the 304 is decided after the page is had: from what is kept, or, on a miss, after a render. A browser's revalidation of a page this process no longer keeps still costs a render.
- **An upload to an id hidden from its uploader is refused as an id they can see is,** 409, `artifact <id> already exists`, at the same point, after its bytes are spooled and before the app reads any of them or anything is stored. Status, body and cost are the same for a taken id either way. Only a visible file with the very same bytes answers otherwise (`unchanged`), which needs its bytes.

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
