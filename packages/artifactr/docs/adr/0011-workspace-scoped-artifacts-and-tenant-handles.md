# ADR-0011: Workspace-scoped artifacts and tenant-scoped handles

**Status:** Accepted
**Date:** 2026-09-28
**Deciders:** Alex Nodeland

## Context

artifactr must be multi-tenant, and concurrent chats should be able to work on the same artifacts. If each chat owns its artifacts, sharing a plan across chats becomes copy-and-link machinery. If tenant ids are passed through every call, a single forgotten or wrong argument becomes a cross-tenant leak.

## Decision

- The hierarchy is **tenant → workspace → {artifacts, threads, log}**. Artifacts belong to the workspace, and threads list the artifacts they are focused on.
- `await workspaces.open(tenant_id, workspace_id, actor=...)` returns a `Workspace` **bound** to that tenant, workspace and actor. Nothing below it accepts a raw tenant id, and every storage query is filtered by the bound scope.
- `ws.as_actor(actor)` returns a handle for another actor in the same scope, which is how the agent's session gets its handle.
- Postgres row-level security can be layered underneath as defence in depth.

## Options considered

### Artifact scope

| Option | Complexity | Cross-chat collaboration |
|---|---|---|
| **Workspace-scoped (chosen)** | Low | Natural: chats share artifacts |
| Thread-scoped | Low | Needs explicit copy or link operations |
| Per type (`scope` class variable) | Medium | Both, with two ownership models to test |

### Tenant isolation in the API

| Option | Complexity | Leak resistance |
|---|---|---|
| **Scoped handles (chosen)** | Low | High: a cross-tenant query cannot be written |
| Explicit scope arguments on every call | Low | Low: one wrong argument leaks |
| A database or schema per tenant | High to operate | Highest, and orthogonal to the API |

## Trade-off analysis

Workspace scope makes concurrent chats on shared artifacts the default rather than a feature, and optimistic concurrency ([ADR-0004](0004-optimistic-concurrency-and-revisions.md)) already handles the conflicts that result. Scoped handles move the isolation check to one constructor instead of every call site. A database per tenant remains an option for deployments that need it, without changing the API.

## Consequences

- Easier: several chats and people collaborate on the same artifacts.
- Easier: tenant isolation is enforced in one place.
- Harder: tenant-level quotas and rate limits live in the host application, not the library.
- Revisit per-type scoping if a use case needs artifacts private to one chat.

## Action items

1. [ ] Implement `Workspaces.open` and scope binding in the workspace layer.
2. [ ] Enforce scope in both storage implementations, with tests that attempt cross-tenant access.
3. [ ] Document optional Postgres row-level security in `artifactr.sql`.
