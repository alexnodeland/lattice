# ADR-0039: The tracker connector's reads, for the portal

**Status:** Accepted
**Date:** 2026-10-18
**Deciders:** Alex Nodeland

Serves phase 3 of [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md), [portalr, later](../../rfcs/0004-relayr-and-task-trackers.md#portalr-later): portalr shows, on a run, the tracker items it was filed as, and, in admin, how the connector is doing in a workspace. portalr's side is [portalr ADR-0046](../../portalr/adr/0046-tracker-links-on-runs.md).

## Context

Everything a run filed is in the ledger, and nowhere else: `relayr_tracker_items` keeps each key's claim, with the chain of the run that claimed it first, and the item it made, as the port's `ItemRef`. A link is the adapter's `link(ref)`, which needs the tenant's base URL and, on Plane, its workspace slug, from the credentials. portalr reads each package through that package's own routes, mounted by the application, and adds routes only for what no package has ([lattice RFC-0002](../../rfcs/0002-portalr-the-portal.md)); its Python side depends on grantr and lattice-core, not on relayr. The `Ledger` port had no read of more than one key, and no record of when a follower last read its project: `swept_at` is the last whole read, and the cursor is the tracker's `updated_at` of the last item read, which stands still while nothing changes.

## Decision

- **Two reads, in `relayr.fastapi`,** beside the webhooks' route, behind the same `fastapi` extra: `tracker_reads_router(trackers, workspaces, resolve_actor=)`.
  - `GET /relayr/v1/workspaces/{workspace_id}/tracker/items`: every item the workspace's runs filed, the newest first by number, each with its key, name, link, whether a person deleted it, and its `chains`: the chain of the run that filed it first, then those of the runs that commented on it. A run is filed as an item when its chain is among them.
  - `GET /relayr/v1/workspaces/{workspace_id}/tracker`: the tracker and its integration's key, the workspace's binding, how far its follower read and when (`reading`), how many items its runs filed, its dead letters, and relayr's writes to each item within the cap's window, with the cap.
- **Refused as reflexr refuses.** A caller `resolve_actor` refuses is 401; a rejection from opening the workspace or from `authorize` gets the status reflexr's routes give it, such as 403 or 422, and each read's span is attributed to its tenant and workspace.
- **Authorized as reflexr's own reads.** A read resolves its caller with the application's `resolve_actor`, the one reflexr's router takes, opens the workspace through reflexr's `Workspaces`, which asks `authorize` for `reflexr:open`, then asks it for the read's action: `reflexr:read_runs` for what runs filed, which is what the runs did, and `reflexr:read_dead_letters` for how the follower is doing, which holds what it could not publish. grantr's roles already hold both where they hold the runs and the dead letters, so no catalog changes. The tenant is the caller's, never a parameter, and the reads go through the ledger's tenant sessions, under row-level security where it is on: nothing is read across tenants.
- **A link needs no request to the tracker.** It is the bound workspace's adapter's `link`: the one its follower or a run already made, or one made with the tenant's credentials as theirs are, cached five minutes. A workspace bound to nothing now has no links, and asks for no credentials. The switch is not asked: a link to an item that exists still opens, and the tracker checks who may see it.
- **The ledger grows three things,** in `InMemoryLedger`, `SqlLedger` and the contract test, on memory, SQLite, PostgreSQL, and PostgreSQL under row-level security:
  - `every_tracked(workspace)`: every key claimed in a workspace, by kind, then key;
  - `tracker_writes(workspace, within=)`: relayr's writes to each item within a window, which the cap already records on the snapshots' rows;
  - `TrackerFollowing.read_at`: when the follower last read its project at all, saved with every read, and only moving forward within a project. Migration `0007` adds the column to `relayr_tracker_followers`, whose tenant policy covers it.
- **An OpenAPI document,** `schemas/relayr.openapi.json`, of both routers, which `moon run relayr:schema` writes and a test holds to them, as reflexr's is held; portalr's client is typed from it.

## Options considered

| Choice | Option | For | Against |
|---|---|---|---|
| Where | **relayr's own routes (chosen)** | The browser calls each package's routes, as RFC-0002 has it; relayr's types stay relayr's, generated, not copied | One more surface for the application to mount |
| | portalr's router, over a port the application fills from relayr's ledger | One router | portalr would declare relayr's models again, or depend on relayr; RFC-0002 keeps portalr's routes to what no package has |
| | The tracker's link in a reflexr event a run publishes | Nothing new to read | A new event type for every run that files; links made at filing, and wrong after a base URL moves |
| Who may read | **reflexr's `authorize`, with its read actions (chosen)** | No new catalog; who may see a workspace's runs sees what they filed | Two of reflexr's actions answer for relayr's data |
| | A `relayr:` catalog in grantr | Its own actions | Every application's catalogs and the template's matrix change, for reads that mirror reflexr's |
| When it last read | **`read_at`, a column (chosen)** | Says that a follower is reading, though nothing changed | A migration |
| | The lease's expiry | No migration | A lease is held while a poll fails; it says nothing of reading |

## Consequences

- portalr links a run to what it filed, and admin can show a workspace's connector, with one read each and no fan-out.
- An application with a tracker mounts `tracker_reads_router` beside `tracker_router`, and names the origin to portalr's `Surfaces(relayr=...)`; one without mounts neither, and portalr asks for nothing.
- What the echo filter drops isn't recorded, so no read can count it; the cap's refusals are counted only in `relayr.trackers.loops`, a metric, and as runs failed with the reason `tracker_loop`.
- Both reads are whole: what runs filed in a workspace, and every item's recent writes, read without a page. A workspace's filed items are what its rules filed, not the project's; a page can come when one needs it.
- Not changed here: a person's change to an item lattice filed, made before the follower first read that item, is the item's first snapshot, and not published as a change. portalr's test application reads the project before its scenarios' edits for that reason.
