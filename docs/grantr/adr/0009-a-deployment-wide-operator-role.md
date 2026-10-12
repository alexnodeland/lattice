# ADR-0009: A deployment-wide operator role

**Status:** Accepted, amended by [ADR-0014](0014-an-operator-enters-a-tenant-by-granting-themselves.md) and [ADR-0019](0019-runtime-actions-and-the-application-role.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Records decision D9 of [lattice RFC-0001][rfc], identity and access, taken with lattice RFC-0002's decisions.

## Context

Someone creates tenants, and sees the stack's shared tools (Langfuse, Grafana, LiteLLM), which aren't tenant-scoped. Without a role for it, whoever runs the deployment uses those tools directly, outside grantr and its audit log.

## Decision

- **`operator` is a role on the deployment,** held by few: it may create tenants and see every tenant, and the stack's shared tools.
- **It is a grant, never a flag:** given and revoked like any role, only by another operator, and recorded in the audit log. `make operator EMAIL=...` grants the first.
- **It doesn't put an operator inside a tenant's workspaces.** Reading a tenant's threads still needs a role there, which an operator can grant themselves, recorded in the audit log.

## Options considered

| Option | For | Against |
|---|---|---|
| **A deployment-wide `operator` role, an audited grant (chosen)** | Cross-tenant access is visible and revocable | One more role to reason about |
| No deployment-wide role | Nothing to build | Whoever runs the deployment works outside grantr, unaudited |

## Consequences

- Easier: portalr's admin UI can show an operator every tenant, through the same checks as everyone else.
- Harder: the first operator needs a path that works before any operator exists.

[rfc]: ../../rfcs/0001-grantr-identity-and-access.md#decisions
