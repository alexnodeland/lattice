# ADR-0033: The tracker port, and runs that write to it once

**Status:** Accepted
**Date:** 2026-10-17
**Deciders:** Alex Nodeland

Builds the outbound half of phase 1 of [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md): the port, the core, the fake and the contract test; the claims and items in the ledger; and both adapters. It follows the RFC's decisions O1 to O4, and its recommendations T3 (a claim in the ledger for both trackers, with Plane's external ids as a second guard), T4 (a tracker user and key per tenant) and T5 (the rule's arguments, with the binding's project and defaults), which the RFC leaves to the maintainer's sign-off. Where the code departs from the RFC's text, this says so, and why.

## Context

RFC-0004 has rules' runs file and update work items in a task tracker. Neither Plane CE nor Vikunja takes an idempotency key, and reflexr retries a failed attempt, so a run that writes naively files an item for each attempt. relayr already makes artifactr writes once by deriving their ids from the run ([ADR-0019](0019-runs-act-once-through-derived-ids-and-keyed-edits.md)); a tracker makes its own ids, so relayr has to remember what it asked for.

## Decision

- **`relayr.trackers` owns the port, `Tracker`, in its own vocabulary,** as the RFC specifies it: `find`, `create`, `item`, `update`, `comment`, `items`, `comments`, `nudge` and `link`, with typed errors (`RateLimited`, `Unavailable`, `NotFound`, `Refused`, `Unauthorized`). `FakeTracker` keeps it in memory. Adapters live in `relayr.plane` and `relayr.vikunja`, behind the `plane` and `vikunja` extras, on plain async httpx; `relayr.trackers.http`, which only they import, maps both trackers' failures and takes 10 s at most per request.
- **The ledger claims every key before anything is sent,** in `relayr_tracker_items`, keyed by tenant, workspace, kind (`item` or `comment`) and key. `claim_tracked` takes a new key, or one claimed more than 30 s ago that never recorded what it made; `record_tracked` keeps the first record. `ensure_item` claims, asks the tracker for an item the key filed, and only then creates one, so a process that died between the create and the record makes nothing twice. A fresh claim held by another attempt fails this one, to be retried (`tracker_claimed`).
- **A row keeps the first claimer's correlation id,** not a cause: nothing that comes back through a tracker will be published with causation (the RFC's "Echoes and loops", phase 2). Rows aren't forgotten after a week, as causes are ([ADR-0025](0025-counters-and-how-long-causes-are-kept.md)): they last as long as the item.
- **A recorded item is read before it is returned.** A deleted one marks the key, and `ensure_item` returns `Deleted` from then on without asking the tracker. Plane frees an external id when an item is deleted, so without the mark a lookup alone would file it again. An archived or closed item is returned.
- **Edits are keyed:** `update` reads the item, sends only the fields that differ, and records the values it sends on the item's key first, for the reading side to tell relayr's changes from people's.
- **Each lattice workspace has its own adapter,** made by `connect(credentials, source)` from its tenant's credentials and its source, `lattice:<tenant>/<workspace>`, which is Plane's `external_source`. Credentials are asked for at most every five minutes, and again at once when the tracker refuses the key; the request is then made once more.

### Where it departs from the RFC

- **One table, not three.** The RFC's migration adds `relayr_tracker_items`, `relayr_tracker_followers` and `relayr_tracker_dead_letters`. The two others hold phase 2's followers, so they come with them: a table nothing writes, behind ledger methods nothing calls, would be untested schema.
- **Comments are claimed in the same table,** as `kind = 'comment'`: the RFC claims comments "the same way" and lists no table for them.
- **Vikunja's marker names the source as well as the key:** `lattice-key: lattice:<tenant>/<workspace>/<key>`, where the RFC has `lattice-key: <key>`. Under T6 every workspace of a tenant may bind the same Vikunja project, and a key such as `dead-letter/<rule>` would otherwise name another workspace's item. Plane's pair already tells them apart.
- **`ItemRef` carries a `name`,** what people call the item (`OPS-12`), beside its `number`. Plane's link is `<base>/<workspace>/browse/<PROJECT>-<number>/`, and `link` is synchronous, so the ref carries the project's identifier rather than the adapter asking for it.
- **A refused edit puts back what was recorded before it,** where the RFC says it "clears its record". The change never landed, so the value relayr set before it is still the last one relayr set; clearing it would make an echo of that earlier write look like a person's.
- **`update` changes only items lattice filed,** which have a key to record values on; a rule may still comment on any item. Changing a person's item waits for phase 2, which keeps a row for every item in a bound project.
- **401 and 403 are both `Unauthorized`.** Plane answers an invalid key with 403 and a missing one with 401; Vikunja answers a token without the scope with 401.
- **Plane's fixtures are not recorded.** The RFC records both trackers' fixtures and runs both live. No Plane was run: its contract test runs against `tests/trackers/plane_api.py`, Plane's API as its v1.4.2 source reads, with each behaviour's source file named there. Vikunja's are recorded from a live v2.7.0 ([ADR-0035](0035-what-phase-1-settled-of-the-trackers-unknowns.md)).

## Options considered

| Option | For | Against |
|---|---|---|
| **A claim in the ledger for both trackers (chosen, T3)** | One mechanism; covers Vikunja, which has no external ids, and Plane's race, which its code-only uniqueness doesn't stop | A table and six ledger methods; a claim held 30 s by an attempt that died delays the retry |
| Plane's external ids alone, and a marker search for Vikunja | Nothing in the ledger | Two racing creates both pass Plane's check, and its lookup then answers 500; Vikunja's search can't stop a race at all |
| An outbox in relayr | Writes survive a tracker that is down | A second retry mechanism beside reflexr's, which is already the outbox |

## Consequences

- A rule writes to a tracker as it acts in artifactr: once per key, however often it is retried, in any order.
- A ledger an application wrote must add the six methods; relayr's two pass the contract test on memory, SQLite and PostgreSQL, with and without row-level security.
- The reading side (phase 2) starts from a ledger that knows every key lattice filed and every value it set.
- Vikunja's marker is visible to people, and whether its editor keeps it is still unverified.
- A request a tracker finishes more than 30 s after relayr gave up could still make a second item on Vikunja, where `find` is a search; on Plane the 409 catches it.
