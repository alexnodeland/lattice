# ADR-0015: A check writes nothing

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [lattice RFC-0001](../../rfcs/0001-grantr-identity-and-access.md)'s model, where a workspace is "registered in grantr when it is first granted or checked".

## Context

`Grants.resources` lists the workspaces, threads, artifacts or rules a subject may act on, such as the workspaces `GET /grantr/v1/me` shows. grantr can only list what it knows. Registering a workspace on every check would make a check a write, and let a refused probe fill the registry with ids.

## Decision

- **grantr knows a workspace, thread, artifact or rule once a grant names it, or an item in it.** Phase 5's restricted flag also makes an item known. A check reads, and writes nothing.
- **`resources` lists workspaces and items,** and returns `Resource`s rather than ids, since an item's id is unique only in its workspace.

## Options considered

| Option | For | Against |
|---|---|---|
| **Known from grants; a check writes nothing (chosen)** | A check stays one read, and a probe registers nothing | `resources` doesn't list a workspace no grant reaches |
| Register on every check, as the RFC says | Every opened workspace is listed | A write per check, and a refused probe fills the registry |

## Consequences

- Easier: phase 3's SQL adapter has no write on the check path.
- Harder: `/me` lists a workspace only once something in it is granted. A tenant-wide role still opens every workspace; listing every workspace is artifactr's (#5), filtered by `check`.
