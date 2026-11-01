# ADR-0041: Bindings stored per tenant beside the operator's, read across tenants for the intake

**Status:** Accepted
**Date:** 2026-11-01
**Deciders:** Alex Nodeland
**Implements:** lattice [ADR-0040](../../adr/0040-bindings-declared-in-lattice-core-stored-by-grantr-beside-the-operators-layer.md)'s action item 2, lattice RFC-0013's bindings; beside [ADR-0035](0035-settings-narrowed-per-tenant-and-workspace-in-grantrs-table-versioned-audited.md) and [ADR-0038](0038-approvals-stored-per-tenant-answered-by-grantrs-subjects-groups-and-grants.md)

## Context

lattice-core declares `Binding` and the `Bindings` port (lattice ADR-0040). RFC-0013 says grantr stores the tenant's bindings, beside the operator's layer from the deployment's configuration, changed by audited commands under `grantr:manage_bindings`, which a tenant's owners and admins hold. Two questions are grantr's to settle:

- **Where the rows go.** Each tenant's rows sit under row-level security.
- **How the deployment's intake reads a connection's bindings in every tenant.** A deployment's connection, such as Alertmanager's, reaches many tenants, and the intake routes each occurrence to the tenant the source names.

## Decision

- **`grantr_bindings`** holds each tenant's bindings (migration 0009):
  - Rows are keyed by tenant and id, with the workspace, source and connection as columns and the binding as JSON.
  - Two indexes after the tenant: one for a connection's bindings, one for a workspace's.
  - The tenant policy every other table has.
- **`Grants.bindings()`** returns `GrantrBindings`, which holds the commands and the port:
  - `bind(tenant, workspace, source, connection, select=, types=, trust=, options=, by=)` returns its audit entry (`binding_added`):
    - It mints the id and records the subject as `by` (`user:alice`).
    - Its `bound_at` is the entry's time.
    - A binding that isn't well formed is `Invalid` before anything is checked or written.
  - `unbind(tenant, id, by=)` returns `binding_removed`. One of the operator's is refused: it is the deployment's configuration.
  - `listed(tenant, by=, workspace=)` returns the operator's, then the tenant's.
  - Each needs `grantr:manage_bindings` on the tenant, which owners and admins hold and no workspace role does: a workspace's admin pauses a source with its `source:<name>` switch instead (RFC-0013).
- **The operator's layer** is `Grants(operator_bindings=...)`, given as the deployment starts and never stored. An id it repeats is refused.
- **`for_connection(source, connection)`** returns the operator's bindings of the connection, then each live tenant's, read tenant by tenant under its own policy, as the approvals sweep reads them. The intake filters them by the occurrence's tenant. **`for_workspace`** reads one tenant's.
- **Deleting a tenant** deletes its bindings.
- **The admin API:** `GET`, `POST /tenants/{tenant}/bindings` and `DELETE /tenants/{tenant}/bindings/{id}`. portalr's admin words both events ("bound forge inst_1 to workspace api, trusted as untrusted").

## Options considered

### Option A: Each tenant's rows, read tenant by tenant (chosen)

**Pros:** every row stays under its tenant's policy, and the intake's read needs no role that crosses tenants.
**Cons:** a connection's bindings take one read per tenant. The intake reads them as a stream starts and as bindings change, not per occurrence, so the cost is per tenant, not per event.

### Option B: An index of connections to tenants, outside row-level security

**Cons:** a table every tenant's transaction could read would say which tenants bind which connections, which is a tenant's business; and it must be kept in step with the rows.

## Consequences

- Easier: an admin binds a source to a workspace in one command, audited, and the intake reads the same type the template's `TRACKER_BINDINGS` becomes.
- Harder: with many tenants, `for_connection` grows with them. A cache in the intake, invalidated by the audit log's `binding_*` entries, is its own change if it is needed.
- portalr's admin page for bindings comes with connections (#927).

## Action items

1. [x] `grantr_bindings`, `GrantrBindings`, `grantr:manage_bindings`, the two events and the admin API, tested on memory, SQLite and PostgreSQL with row-level security.
2. [ ] The template's `TRACKER_BINDINGS` read as the operator's layer (RFC-0013).
3. [ ] Admin's page for bindings (#927).
