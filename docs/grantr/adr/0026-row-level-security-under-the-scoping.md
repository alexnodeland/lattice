# ADR-0026: Row-level security under the scoping

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends lattice [RFC-0001](../../rfcs/0001-grantr-identity-and-access.md#row-level-security): the second engine runs as the tables' owner, not a third role with `BYPASSRLS`; and a transaction that names no tenant sees nothing, rather than failing.

## Context

Lattice RFC-0001 makes PostgreSQL's row-level security a second line of defence under each SQL adapter's own tenant scoping: each transaction names its tenant in `lattice.tenant_id`, policies show it only that tenant's rows, and the work that spans tenants runs on a second engine. grantr differs from the libraries in two ways. Every tenant's checks read the deployment's grants, the application's role among them. And three of its reads are asked before the tenant is known.

## Decision

- **`SqlStorage(engine, row_level_security=True, across_tenants=owner_engine)`.** Each session is a `TenantSession` with its tenant, or `~deployment`, in its `info`, and sets `lattice.tenant_id` with `set_config(..., true)` as its transaction begins, so a pooled connection never carries a tenant on. A session that names no tenant can't begin a transaction. The option is off by default, and does nothing to set on SQLite.
- **Migration 0003 creates the policies on PostgreSQL only,** enabled and not forced, and `create_schema` the same ones. Each table has one that keeps every command to the transaction's tenant, for reading, changing and adding rows alike, and `grantr_grants` and `grantr_group_members` a second that lets any tenant *read* the deployment's rows, which its checks need. A deployment transaction names `~deployment`, so it reads and writes only the deployment's rows.
- **`migrate(engine, application_role=...)` grants a role that owns nothing the tables,** their sequences and the schema, so the application connects as it; the role must exist. Granting again changes nothing.
- **A transaction that names no tenant, or an empty one, sees nothing.** The policies read `current_setting('lattice.tenant_id', true)`, which is null or empty then, and no row's tenant is either. The RFC had such a transaction fail; a session can't begin one anyway, so the policies need only fail closed.
- **Three reads span tenants, and only they use `across_tenants`:** `tenant_grants`, for a user's memberships; `key`, to find a key's tenant; and `tenants`, for operators. `ACROSS_TENANTS` lists them, and a test checks that no other method uses that engine.
- **The second engine runs as the tables' owner,** which the migrations run as and the unforced policies don't hold, rather than a third role with `BYPASSRLS`. The application then has two roles: the owner, for migrations and the reads across tenants, and a role that owns nothing, for everything else.

What a transaction sees and writes under the policies:

| Rows | Read | Changed, deleted or added |
|---|---|---|
| Its tenant's | Yes | Yes, and only to stay its tenant's |
| The deployment's grants and group members | Yes: a check reads the application's and operators' grants | No |
| The deployment's other rows: its audit log, keys, roles and groups | No | No |
| Another tenant's | No | No |
| Any, when the transaction names no tenant | No | No |

## Options considered

| Option | For | Against |
|---|---|---|
| **The owner as the second engine (chosen)** | Two roles to create and keep; the owner bypasses its own tables' policies already | The reads across tenants could also change the schema, if one were wrong |
| A third role with `BYPASSRLS`, as the RFC says | That engine can't change the schema | A third role and password, and `BYPASSRLS` needs a superuser to grant |
| Policies that let the deployment's transaction read every tenant | No second engine | The deployment's own session would see every tenant, which is what the policies are for |

## Consequences

- Easier: the contract test runs again as a role the policies hold, so a query that isn't scoped to its tenant fails in tests, not in production.
- Harder: an application that turns the option on connects with two URLs, creates its non-owner role before it migrates, and passes it to `migrate`.
