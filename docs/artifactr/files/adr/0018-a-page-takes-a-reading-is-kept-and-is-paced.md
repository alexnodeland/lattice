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

## Amendment (2026-10-23): the waiters, bounded, and what wasn't built

The review's follow-ups ([lattice #570](https://github.com/alexnodeland/lattice/issues/570)):

- **A page waits for a reading by looking again, not in turn.** Each waiter looks every `LOOK_AGAIN` (50 ms), and whichever looks first after a reading is freed takes it: an earlier waiter can lose every race until its deadline and be refused, `Busy`, 429 with `Retry-After`, which the client retries. A waiter's last sleep is cut to what is left of its deadline, so the deadline is exact.
- **A tenant's waiters are bounded:** `NativeFiles(waiting=8)`, twice the pages a viewer's first screen asks for. Past it, a page is refused at once, so one tenant's pages cost at most eight looks every 50 ms between them, about 160 wakeups a second.
- **A page that waited finds one rendered meanwhile:** a page that gets a reading looks again in the pages kept, and is given the one another render kept while it waited, without the app or the reader's pace. Two pages asked for at the same moment, each with a reading free, both render: no in-flight map is shared, since a waiter on it would need a primitive of one event loop's.
- **A page is kept, and found, by the blob, as the blob store keeps bytes:** the tenant, the workspace, the file and the digest, with the app, the page and the scale. A proposal's page is found by the digest its patch names without hashing its bytes. That digest is the proposer's to write, so it finds only a page kept for the same file's bytes in the same workspace: never one kept for another tenant's, or another file's, that names the same digest. A page kept is of bytes the file holds: collection drops the pages of the bytes it may delete, those nothing names, so a digest whose bytes are gone finds no page. On a miss the bytes are read from the store, and a digest the file doesn't have is refused, `ContentUnavailable`, as before. A proposal that changes no content is refused before it takes a reading or its reader's pace.
- **portalr's client waits a little more, at random,** before it asks again after a refusal: up to a fifth past the server's `Retry-After`, or its own backoff, so the pages a busy server refused together don't come back together.

Not built, and why:

- **A condition per tenant, to wake a waiter rather than have it look.** asyncio's and anyio's conditions belong to one event loop, and a waiter on one is never woken from another; an application, or its tests, can serve requests on several, which is what the store's own asyncio lock hung on (lattice #594). Looking again works on any loop, and the cap bounds what it costs.
- **Cancelling a render when its reader goes away.** The worker does the call once it has it, whatever the application does, and does one at a time: cancelling the application's side frees no turn of the worker's. The reading is held until the render ends, at most the app's deadline, as an upload's is.
