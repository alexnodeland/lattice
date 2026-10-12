# ADR-0058: A tenant's workspaces, listed by what each actor may open

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0056](0056-access-asked-in-every-workspace-method.md), where artifactr always names the workspace it asks `authorize` about.

## Context

artifactr opens a workspace by id, but can't list the workspaces a tenant has ([lattice #5](https://github.com/alexnodeland/lattice/issues/5)). Two readers need the list:

- **relayr starts a follower per workspace** ([stackr RFC-0002](../../stackr/rfcs/0002-the-combined-system.md), phase 3). Without a list, a follower starts only when its workspace is first used, and a workspace that hasn't been used since a restart is not followed.
- **A UI shows the workspaces a person can open.** grantr can't: a check writes nothing, so grantr knows a workspace only once a grant names it ([grantr ADR-0015](../../grantr/adr/0015-a-check-writes-nothing.md)). That ADR leaves listing every workspace to artifactr, filtered by the check.

artifactr has no registry of workspaces. No command creates a workspace; `SqlStorage` keeps a row per workspace from its first transaction, and a workspace counts as existing once its log has an event.

## Decision

- **`Storage.workspaces(tenant_id, *, after=None, limit=100)`** returns a page of a tenant's workspace ids, ordered by id as the storage orders strings, after `after`. It is the first storage method that spans a tenant rather than one workspace.
- **A workspace is listed once its log has an event.** Reading a workspace, or keeping its cursors or leases, doesn't list it, so a probe of an unknown id leaves nothing behind. `SqlStorage` lists the `artifactr_workspaces` rows with `head_seq > 0`, through their primary key, with no migration.
- **`Workspaces.list(tenant_id, *, actor, after=None, limit=100)`** asks `authorize` for `artifactr:read_workspaces` with no workspace, as reflexr's tenant-wide reads do. It then asks `artifactr:open` in each workspace it finds, and leaves out those refused. It opens none of them, so `on_open` is not called and listing has no side effects.
- **A page is full unless the list has ended.** `list` reads storage until it has `limit` workspaces the actor may open, or storage has none left. The last id is the next page's `after`, and a short page is the last.
- **Paging is by key, so it doesn't see behind its cursor.** A workspace created mid-scan with an id before the cursor is missed by that scan; relayr's start on first use picks it up.
- **`artifactr:read_workspaces` joins `ACTIONS`.** It is the one action artifactr asks with no workspace; `Authorize` keeps its signature.
- **REST and MCP list through it:** `GET /workspaces?after=&limit=` returns the ids as a JSON array, and the `list_workspaces` tool returns one per line. Both take the tenant from the caller's credentials. A refusal is 403 or a tool error, and a `limit` below 1 is 422, which the OpenAPI document states as a minimum, or a tool error.

## Options considered

### Option A: filtered by `artifactr:open`, page-filling (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one loop over storage pages |
| Surfaces | Every surface lists what its caller may open, through one method |
| Cost | One hook call per workspace read |

**Pros:** what a caller sees is what it could open, everywhere; the page shape is a plain list.
**Cons:** a caller who may open few of many workspaces costs a hook call for each it can't. In the worst case, one page for a user who may open few of a tenant's N workspaces scans the whole tenant: N hook calls, and N grantr queries.

### Option B: list every workspace once `read_workspaces` allows it

| Dimension | Assessment |
|---|---|
| Complexity | Lowest |
| Surfaces | Leaves filtering to each application |

**Pros:** one hook call per page.
**Cons:** names workspaces to callers who may not open them, and a UI must filter with grantr's batch check itself. ADR-0015 asks for the opposite.

### Option C: filtered, returning a page with a cursor

Each storage page is filtered once, and the result carries the last id read as `next`, so a page may be short or empty before the end.

**Pros:** a bounded number of hook calls per request.
**Cons:** a page model and an end marker on every surface, and an empty page that is not the end.

## Trade-off analysis

The reader that matters most for correctness is a person's UI, which must not see workspaces they can't open. Filtering inside `Workspaces.list` gives that on every surface without a second hook. Page-filling keeps the shape a list of ids, which REST, MCP and relayr all use as-is; a short page meaning the end is a rule each caller already knows from `read`. The cost of a hook call per refused workspace is the price of ADR-0015's division of work, and grantr answers each check with one indexed query.

## Consequences

- Easier: relayr can start a follower for every workspace at start-up, through a system actor that may open them all (stackr RFC-0002, phase 3).
- Easier: a UI lists exactly the workspaces its user may open.
- Harder: every `Storage` implementation adds `workspaces`; the behaviour suite checks it.
- Harder: an `authorize` hook now hears a `None` workspace from artifactr, for `artifactr:read_workspaces`.
- Revisit: if listing a large tenant for a narrowly granted user becomes slow, a batch form of the hook, or a hook that lists: grantr's `workspaces(tenant, member)` or `resources(...)` lists the workspaces a member is granted in about one query, and a tenant-wide grant falls back to the unfiltered list.

## Action items

1. [x] `Storage.workspaces` in `InMemoryStorage` and `SqlStorage`, with contract tests.
2. [x] `Workspaces.list`, `artifactr:read_workspaces`, the REST route and the MCP tool, in the permission matrix.
3. [ ] relayr starts its followers from the list (stackr RFC-0002, phase 3).
