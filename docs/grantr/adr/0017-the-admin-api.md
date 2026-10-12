# ADR-0017: The admin API

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Lattice RFC-0001 gives grantr a FastAPI router, `grantr_router(grants, resolve_actor=...)`, for tenants, members, groups, roles, grants, keys and the audit log, two reads for UIs (`/me` and `/checks`), and the libraries' error shapes. A user names a tenant on each request, but a service principal's key belongs to one tenant, and the same principal id may exist in two. grantr's catalog has `grantr:read_audit` and no other read.

## Decision

- **`resolve_actor` returns a `Caller`:** the subject, and the one tenant it may act in, for a key. The router refuses a bound caller every other tenant, with 403, so a key can't reach another tenant through the API either.
- **Each list is read with the action of the command that changes it:** members with `grantr:add_member`, groups with `grantr:manage_groups`, custom roles with `grantr:define_role`, grants with `grantr:grant` on the tenant or the workspace, keys with `grantr:issue_key`, and tenants with `grantr:create_tenant`. The catalog stays as the RFC lists it.
- **`/me` and `/checks` are for members.** The tenant is `X-Tenant`, or a key's, or a user's only one; with none and several memberships the request is 400, and a caller who isn't a member is 403. `/me` without a tenant lists the caller's memberships. Its workspaces are those where the caller holds any library's `open`.
- **Refusals keep the libraries' shapes,** a `detail` of `{"type": ..., "message": ...}`: 401 `unauthorized` without a caller, 403 `forbidden`, 422 `invalid` for a command that can't apply, and 400 `tenant_required` for a missing tenant. FastAPI's own 422 for a malformed request keeps its list-shaped `detail`.
- **Requests are bounded:** `after_seq` is at least 0, `limit` is 1 to 1,000 (100 by default), and `/checks` takes at most 100 questions.
- **Revoking is `POST /tenants/{tenant}/revocations`,** with the grant as its body, rather than `DELETE` with a body.
- **The paths are relative,** and an application mounts the router at `/grantr/v1`. The committed OpenAPI document is generated from a bare application that does, and a test holds it to the router.

## Options considered

| Option | For | Against |
|---|---|---|
| **A `Caller` with the key's tenant (chosen)** | A key's tenant reaches every route | One more type for applications |
| `(tenant, subject)`, as the libraries' resolvers | Familiar | A user has no one tenant, and admin routes name theirs |
| **Lists read with their commands' actions (chosen)** | No new actions; whoever changes a list can see it | Reading a list needs the right to change it |
| New `read_*` actions in grantr's catalog | Finer | A change to the RFC's catalog, and to phase 4's matrix |

## Consequences

- Easier: portalr's admin UI reads and changes access through one router, typed from the committed document.
- Harder: a member can't list a tenant's members without being able to add one.
