# ADR-0066: Row-level security under the scoping

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Every read and write of `SqlStorage` names its tenant, and every primary key starts with it ([ADR-0021](0021-sql-storage.md)). Lattice RFC-0001 adds PostgreSQL's row-level security under that scoping, as a second line of defence: a query that forgot its tenant should still see no other tenant's rows.

## Decision

- **`SqlStorage(engine, row_level_security=True)`.** Each session is a `TenantSession` with its tenant in its `info`, and sets `lattice.tenant_id` with `set_config(..., true)` as its transaction begins, so a pooled connection never carries a tenant on. A session that names no tenant can't begin a transaction. The leases, which were written on the engine directly, now go through the same sessions. The option is off by default, and does nothing to set on SQLite.
- **Migration 0006 creates the policies on PostgreSQL only,** enabled and not forced, on every table, and `create_schema` the same ones: a transaction reads, changes, deletes and adds only the rows of the tenant it names, and can't move a row to another. The tables' owner, which the migrations run as, isn't held by them.
- **`migrate(engine, application_role=...)` grants a role that owns nothing the tables,** their sequences and the schema, so the application connects as it; the role must exist. Granting again changes nothing.
- **A transaction that names no tenant, or an empty one, sees nothing,** rather than failing as lattice RFC-0001 has it: the policies read `current_setting('lattice.tenant_id', true)`, which is null or empty then, and no row's tenant is either. A session can't begin such a transaction anyway, so the policies need only fail closed.
- **artifactr needs no second engine:** every read is in one tenant, `Workspaces.list` included.

## Options considered

| Option | For | Against |
|---|---|---|
| **A session per tenant that sets the tenant as its transaction begins (chosen)** | Every statement in the transaction is covered, including those SQLAlchemy issues itself | Each transaction runs one more statement |
| Set the tenant per connection when it is checked out | One statement per checkout | A pooled connection could carry one tenant into another's work |

## Consequences

- Easier: the workspace suite runs again as a role the policies hold, so a query that isn't scoped to its tenant fails in tests.
- Harder: an application that turns the option on creates a role that owns nothing before it migrates, passes it to `migrate`, and connects as it.
