# ADR-0062: Row-level security under the scoping

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Every read and write of `SqlStorage` names its workspace, and so its tenant, and every primary key starts with the tenant ([ADR-0030](0030-sql-storage.md)). Lattice RFC-0001 adds PostgreSQL's row-level security under that scoping, as a second line of defence, as artifactr's and grantr's adapters have it. reflexr differs from artifactr in one way: its dispatcher lists every tenant's workspaces, and its scheduler finds every tenant's due runs, so two of its reads span tenants.

## Decision

- **`SqlStorage(engine, row_level_security=True, across_tenants=owner_engine)`.** Each session is a `TenantSession` with its workspace's tenant in its `info`, and sets `lattice.tenant_id` with `set_config(..., true)` as its transaction begins, so a pooled connection never carries a tenant on. A session that names no tenant can't begin a transaction. The leases, which were written on the engine directly, now go through the same sessions. The option is off by default, and does nothing to set on SQLite. `reflexr.sql.tenancy` is the same code as artifactr's and grantr's.
- **Two reads span tenants, and only they use `across_tenants`:** `workspaces`, the dispatcher's, and `due_runs`, the scheduler's. `ACROSS_TENANTS` lists them, and a test checks that nothing else in the module uses that engine. It runs as the tables' owner, as grantr's does ([grantr ADR-0026](../../grantr/adr/0026-row-level-security-under-the-scoping.md)).
- **Migration 0007 creates the policies on PostgreSQL only,** enabled and not forced, on every table, and `create_schema` the same ones: a transaction reads, changes, deletes and adds only the rows of the tenant it names, and can't move a row to another.
- **`migrate(engine, application_role=...)` grants a role that owns nothing the tables,** their sequences and the schema; the role must exist. Granting again changes nothing.
- **A transaction that names no tenant, or an empty one, sees nothing,** rather than failing as lattice RFC-0001 has it, as in artifactr and grantr.

## Options considered

| Option | For | Against |
|---|---|---|
| **The scheduler's and dispatcher's reads on the owner's engine (chosen)** | They see every tenant, and nothing else can | Two engines to configure |
| A deployment tenant the policies let read every row | One engine | The application's own sessions could then read every tenant |

## Consequences

- Easier: the workspace suite runs again as a role the policies hold, with the scheduler's due runs found in every tenant, so a query that isn't scoped to its tenant fails in tests.
- Harder: an application that turns the option on connects with two URLs, creates its non-owner role before it migrates, and passes it to `migrate`.
