# ADR-0035: What phase 1 settled of the trackers' unknowns

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Records what [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md#unverified)'s phase 1 found of its [Unverified](../../rfcs/0004-relayr-and-task-trackers.md#unverified) list, which its exit criteria ask to settle, record as fixtures and write down here. Vikunja was run; Plane was not.

## Context

The RFC was written from both trackers' source, read and not run. Its phase 1 settles what the source left open against the pinned releases: Vikunja v2.7.0 and Plane v1.4.2.

- **Vikunja v2.7.0** ran on PostgreSQL 17, from the image `relayr`'s `compose.yaml` now pins (`moon run relayr:vikunja-up`), driven through its REST API with a scoped API token. The contract test's exchanges were recorded from it, into `tests/trackers/fixtures/vikunja/`, with one real webhook delivery.
- **Plane v1.4.2** was not run: it is 13 services and 4 to 8 GB, and makes its users and keys only in its web app. Its API was read again at the `v1.4.2` tag, `apps/api/plane/`, with Django REST framework 3.17.1 and requests 2.33.0, the versions it pins. `tests/trackers/plane_api.py` answers as that source does, and names the file each behaviour comes from.

## Decision

### Settled on a live Vikunja

- **Its signature** is HMAC-SHA256, lowercase hex, in `X-Vikunja-Signature`, over the exact bytes it sends: checked on real deliveries, one of which is the nudge fixture.
- **An API token registers a webhook,** with the `projects_webhooks` scope: `PUT /projects/{id}/webhooks` with a secret and the events. Deliveries carry `{event_name, time, data}`, with `data.project.id`, `data.task` and `data.doer`.
- **What moves `updated`:** marking done or not, priority, title, description, adding one label, removing one, and a new comment each move it, to the second. Setting labels in bulk (`POST /tasks/{id}/labels/bulk`) doesn't, so the adapter adds and removes them one at a time. Assignees weren't tried: relayr's token has no scope for them.
- **The filter `updated > <time>`,** with `sort_by=updated&sort_by=id`, works on PostgreSQL, to the second Vikunja keeps. On SQLite, `updated >= <second>` missed tasks updated within that second, so the adapter asks from the second before the cursor's and drops what isn't after it.
- **`POST /tasks/{id}` sets every field,** and zeroes those it isn't sent: a partial update wiped a task's description and priority. The adapter reads the task and sends it whole.
- **The marker survives the REST API,** and `s=` finds it within a project; but `s` matches a substring, so `dead-letter/run_1` also finds `dead-letter/run_10`. The adapter matches the whole marker, at the end of the text, and a contract test checks it.
- **Comments are listed newest first;** the adapter orders them oldest first.
- **Registration is rate-limited** for requests without a key; the contributor stack raises the limit so live runs can register their own user.

### Settled from Plane's source

- **Its signature's bytes equal its body.** It signs `json.dumps(payload)` with the standard library's defaults, and sends `json=payload` through requests, which serializes with the same defaults (simplejson isn't installed). The adapter verifies the raw body, and never re-serializes it, so the RFC's fallback isn't needed.
- **`updated_by`** is null on a create, and the key's user on a `PATCH`, set by crum in the model's `save`.
- **Bot users** exist in the model (`is_bot`, and API tokens' `user_type`), but nothing in the API makes one, and authentication doesn't treat them apart. `relayr-<tenant>` is an ordinary user.
- **An invalid key is 403,** not 401; a missing one is 401. Both are `Unauthorized`.
- **External ids:** a used pair is a 409 with the existing `id`, for items, comments and labels; an item's lookup by the pair reads archived, draft and triage items, which its read by id and its list leave out; a deleted item frees its pair.
- **Lists** are pages of `results`, by a cursor `<per_page>:<page>:0`, 1000 at most. Comments and labels are listed newest first whatever `order_by` says.

### Still unverified

- **On Plane, everything live,** and in particular what moves a work item's `updated_at` besides a `PATCH` (a new comment, among others), and whether its browse link takes a trailing slash. The nightly live run the RFC plans comes with stackr's Plane recipe.
- **On Vikunja,** whether its web editor keeps the marker when a person edits a description, and its bot users.
- **Plane's activities' shape,** needed only if T1's alternative is chosen.

### A finding against the RFC

**Plane v1.4.2 sends no webhook when a work item or a comment is deleted,** from its API or its web app: only a project's deletion calls `webhook_activity` with `deleted`. The RFC's "Reading back" finds removals through "a Plane delete webhook [that] carries only the item's id", and the daily sweep. Phase 2 has the sweep alone on Plane, unless a later Plane sends the webhook; the RFC's text should be amended when phase 2 is designed in detail.

## Consequences

- The Vikunja adapter's three workarounds (whole updates, labels one at a time, whole-marker matching) are each pinned by a recorded exchange, and re-recorded with `RELAYR_RECORD=1`.
- Phase 1's exit criteria are met for Vikunja and the fake, and for Plane only against its source. A live Plane, its recorded fixtures and the nightly run remain, with stackr's recipes.
