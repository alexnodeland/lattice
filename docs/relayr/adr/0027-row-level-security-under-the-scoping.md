# ADR-0027: Row-level security under the scoping

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Every read and write of `SqlLedger` names its workspace, and so its tenant, and every primary key starts with the tenant. Lattice RFC-0001 adds PostgreSQL's row-level security under that scoping, as a second line of defence, as artifactr's, reflexr's and grantr's adapters have it. One of the ledger's reads spans tenants: `followed`, the workspaces a follower has held, which the followers start from.

## Decision

- **`SqlLedger(engine, row_level_security=True, across_tenants=owner_engine)`.** Each session is a `TenantSession` with its workspace's tenant in its `info`, and sets `lattice.tenant_id` with `set_config(..., true)` as its transaction begins, so a pooled connection never carries a tenant on; one that names none can't begin a transaction. The option is off by default, and does nothing to set on SQLite. `relayr.sql.tenancy` is the same code as the libraries' and grantr's.
- **`followed` is the one read on `across_tenants`,** an engine as the tables' owner ([grantr ADR-0026](../../grantr/adr/0026-row-level-security-under-the-scoping.md)). `ACROSS_TENANTS` names it, and a test checks that nothing else in the module uses that engine.
- **Migration 0004 creates the policies on PostgreSQL only,** enabled and not forced, on its three tables, and `create_schema` the same ones: a transaction reads, changes, deletes and adds only the rows of the tenant it names, can't move a row to another, and sees nothing when it names none.
- **`migrate(engine, application_role=...)` grants a role that owns nothing the tables,** their sequences and the schema. The role must exist, so it is created before the first migration; granting again changes nothing.
- **A transaction that names no tenant, or an empty one, sees nothing,** rather than failing as lattice RFC-0001 has it, as in the libraries and grantr: the policies read `current_setting('lattice.tenant_id', true)`, which is null or empty then, and no row's tenant is either.

## Options considered

| Option | For | Against |
|---|---|---|
| **`followed` on the owner's engine (chosen)** | The followers start in every tenant, and nothing else reads across them | Two engines to configure |
| The followers start per tenant, from grantr's list | No read across tenants | relayr would need the list of tenants, which it doesn't depend on |

## Consequences

- Easier: the ledger's suite runs again as a role the policies hold, so a query that isn't scoped to its tenant fails in tests.
- Harder: an application that turns the option on gives the ledger two engines, as it does the libraries.
