# ADR-0040: Approvals over the admin API, read by who may answer them, answered on portalr's pages

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0011](../../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s grantr and portalr rows, what portalr's approvals page and confirm page read and answer; beside [ADR-0038](0038-approvals-stored-per-tenant-answered-by-grantrs-subjects-groups-and-grants.md)

## Context

grantr's store holds approvals and decides who may answer them (ADR-0038), but only in process: nothing over HTTP lists, reads or answers one. portalr's approvals page and its confirm page, where a caller confirms their own `admin_high` call (lattice ADR-0038, RFC-0014's `/portalr/admin/confirm/{id}`), need all three, through the admin API portalr already calls.

An approval shows a call's arguments, so it is not everyone's to read. An answer names the surface it was given on, and a caller's own confirmation is answered on `portalr:confirm` alone (lattice ADR-0035).

## Decision

Three paths in the admin API, each for a member of the tenant it names:

- **`GET /tenants/{tenant}/approvals`** lists the pending approvals the caller may answer, oldest first. They come from every workspace, or from one with `?workspace=`. It is the store's new `answerable(tenant, subject)`, or its `pending(scope, subject)` for one workspace.
- **`GET /tenants/{tenant}/approvals/{id}`** is one approval as it stands, whatever its state. It is the store's new `shown(id, subject)`:
  - Shown to whoever may answer it, and to the person it was asked for, the caller or the person a run acted for, so they see where it stands.
  - Each must still be a member of its tenant.
  - Anyone else is told it isn't there (404 `not_found`), as is an approval of another tenant than the path's.
- **`POST /tenants/{tenant}/approvals/{id}/answer`** answers it as the caller, with `{approved, arguments_digest, reason?, surface}`:
  - `surface` is `portalr`, the approvals page, or `portalr:confirm`, the confirm page. Nothing else is accepted (422), so no client of the admin API answers as another surface.
  - The store's rules decide who may answer. One who may see it but not answer it, or not on that surface, is refused (403 `forbidden`).
  - A later answer, or one past the deadline, is a 409 (`invalid_state`); the approval, read again, shows the first.
  - An answer to other arguments than the approval's is a 409 (`version_conflict`).
- **Each path answers `ApprovalView`:** lattice-core's `Approval`, field for field, which a test holds. Its answerer is `ApprovalAnswerer`, since lattice-core's answerer and grantr's own subjects are both named `Subject`, and the document would otherwise rename grantr's.
- **Refusals use reasons portalr already words:** `not_found` and `invalid_state` join the router's `STATUS_CODES`, beside `version_conflict`.
- **`grantr:read_approvals`,** which RFC-0011 names, isn't added: no one but an answerer or the person asked for reads an approval yet. It comes with admin's view of every approval in a tenant.

## Options considered

### Option A: The store's answerers, and the person asked for (chosen)

**Pros:** what decides who may answer decides who may read, on every storage, with no grant to keep in step. The person whose run waits sees where it stands.
**Cons:** an admin who can't answer an approval can't see it, until `read_approvals` comes.

### Option B: Anyone who can open the workspace

**Cons:** an approval's arguments may hold what the call would send or change, which a workspace's viewers shouldn't read before anyone decides.

### Option C: The surface taken from the request, not the body

**Cons:** nothing in a request says which page made it. A page names its surface, and the store holds a confirmation to its one caller, never a service principal.

## Consequences

- Easier: portalr's approvals page and confirm page read and answer through the client's generated types, with the refusals they already word.
- Harder: a client holding a person's own session token could answer as either of portalr's surfaces, a confirmation included. Today only portalr holds one. portr, when it comes, holds tokens of its own, and grantr's refusal of `portalr:confirm` to a token a connection holds, as RFC-0014 asks, is decided with them.
- To revisit: `grantr:read_approvals` and admin's view of every approval.

## Action items

1. [x] `answerable` and `shown` in the store, tested on memory, SQLite and PostgreSQL with row-level security; the three paths, tested over HTTP; the OpenAPI document and the client's types.
2. [ ] portalr's approvals page and confirm page on these paths.
3. [ ] `grantr:read_approvals`, with admin's view of every approval.
