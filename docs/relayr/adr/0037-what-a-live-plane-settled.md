# ADR-0037: What a live Plane settled

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Settles what [ADR-0035](0035-what-phase-1-settled-of-the-trackers-unknowns.md) left unverified on Plane, which phase 1 read from its source and never ran. It amends ADR-0035's "Still unverified".

## Context

[lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md)'s phase 1 exit criteria record both trackers' fixtures and settle its [Unverified](../../rfcs/0004-relayr-and-task-trackers.md#unverified) list against the pinned releases. Vikunja v2.7.0 was run; Plane's contract test ran against a stand-in written from its v1.4.2 source.

Plane CE v1.4.2 was run from its unmodified images, pinned by tag and digest, on a contributor's machine, bound to 127.0.0.1: the API, the worker, the migrator, the web app and the proxy, with PostgreSQL 15.7, Valkey 7.2.11 and RabbitMQ 4.1.4, about 1.7 GiB of memory in all. Object storage was left out. Plane's contract test runs against it live with `RELAYR_TEST_PLANE_URL`, which signs up a user of its own through the web app's session API, makes a workspace, an API key, and a project per test. Its exchanges are recorded into `tests/trackers/fixtures/plane/`, as Vikunja's are, with a real webhook Plane signed.

## Decision

### Settled on a live Plane

- **Every write moves `updated_at`, twice:** once as it is made, and again a few hundred milliseconds later, when Plane's worker saves the item's activity. A patch of the name, description, state, priority, labels or assignees each moves it; so does a patch that changes nothing, and a create.
- **A comment moves its item's `updated_at`,** and so do editing and deleting one, through the worker. The follower reads comments when an item's `updated_at` moves, so on both trackers a new comment is found by the poll after it, and the RFC's fallback, polling open items' comments, isn't needed.
- **`updated_by` is who last patched the item:** null on a create, the key's user on a patch, and unchanged by a comment. The follower names it as `actor` only when nothing relayr wrote is among the changes it read ([ADR-0036](0036-reading-a-tracker-back.md)).
- **No webhook on a delete,** of a work item or a comment, nor on an archive or a patch that changes nothing: confirmed live, as ADR-0035 read it from the source. Removals are found by the sweep alone.
- **The webhooks Plane sends:** `issue` created and updated, with the item in `data` and its project's id in `data.project`; `issue_comment` created and updated; `project` created, which names no project and so nudges nothing.
- **Its signature** is HMAC-SHA256, lowercase hex, in `X-Plane-Signature`, over the exact bytes it sends, on every delivery: `json.dumps(payload)` is the body.
- **A comment on a deleted item is made:** Plane deletes softly, so the item still resolves for its comments, and answers 201, while the item's read, patch and lookup answer 404. The adapter reads the item before it comments, and refuses with `NotFound` as Vikunja does.
- **Descriptions and comments read back byte for byte** as relayr sent them: Plane normalises neither, so values recorded before a write compare equal when read back.
- **No bot user can be made:** only the seeding of a new workspace writes `is_bot`, and a bot can't sign in for a key. `relayr-<tenant>` is an ordinary user.
- **An invalid key is 403, a missing one 401,** as read; past `API_KEY_RATE_LIMIT` Plane answers 429 with `Retry-After` in seconds.
- **Lists** leave archived items out, and their read by id answers 404; the lookup by external ids reads them; a reused pair is 409 with the existing id, archived items included. Archiving is the web app's alone, and only of a completed or cancelled item.
- **Its browse link** works with and without the trailing slash.

### Still unverified

- **On Vikunja,** whether its web editor keeps the marker when a person edits a description, and its bot users.
- **Plane's activities' shape,** needed only if T1's alternative is chosen.
- **The nightly live run** the RFC plans: the live runs here were made by hand. It comes with stackr's Plane recipe, and must wait a second after each write for the worker's second touch, as the live harness does.

## Consequences

- Both adapters' contract tests replay exchanges recorded from the pinned releases, and run live against them; no part of Plane's is derived from its source any more. `tests/trackers/plane_api.py` stays, for the adapter tests that need a Plane to misbehave.
- A follower over either tracker reads a person's change, their comment and their deletion, and none of relayr's own, in a contract test recorded live on both.
- A live Plane needs the worker's second touch waited for: a read straight after a write can find the item changed once more.
