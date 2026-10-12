# ADR-0016: The SQL adapter

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0013](0013-transactions-by-tenant-and-one-audit-log.md), whose reads that span tenants gain a third.

## Context

Phase 3 adds grantr's SQL adapter, on SQLAlchemy's asyncio extension and Alembic, as artifactr's and reflexr's are, and runs the contract test on SQLite and PostgreSQL. Lattice RFC-0001 lists ten `grantr_` tables and one index for checks, `(tenant_id, resource_id, subject_id)`. It doesn't say how a subject or a resource becomes a key, how the deployment, which is in no tenant, fits tables keyed by tenant, or how a transaction is serialized.

## Decision

- **Seven tables now:** `grantr_tenants`, `grantr_grants`, `grantr_groups`, `grantr_group_members`, `grantr_roles`, `grantr_keys` and `grantr_audit`, with grantr's own Alembic version table. The other three arrive with what they hold: `grantr_users` and `grantr_principals` with the display names the template caches (phase 4), and `grantr_resources` with the restricted flag (phase 5); [ADR-0015](0015-a-check-writes-nothing.md) needs no registry before then.
- **A subject and a resource are stored in typed columns:** `subject_kind`, `subject_workspace` (a rule's) and `subject_id`, and `resource_kind`, `resource_workspace` and `resource_id`, with an empty string for a part a kind doesn't have, so no primary key holds a null. A grant's primary key is its tenant, resource, subject and role, which leads with the RFC's index for a check and makes a grant unique. A group member is its kind and id, and a key's principal its id.
- **Every query has an index that leads with its filter:** the primary key for a check and a tenant's reads; `(subject_kind, subject_id, tenant_id)` for a user's grants across tenants; `(tenant_id, resource_workspace)` for a workspace's grants; `(tenant_id, member_kind, member_id)` for a member's groups; and the audit log's `(tenant_id, seq)`.
- **The deployment is the tenant `~deployment`** in every table. A tenant id is constrained to have no `~` and not be empty, and the adapter refuses to store one that does, so no tenant's rows can be the deployment's, and a transaction that set no tenant can't match them under phase 6's policy. The deployment's rows have a primary key like any other, so a second identical operator grant is refused by the database.
- **A transaction locks its tenant's row** in `grantr_tenants` (`SELECT ... FOR UPDATE`), inserting it first if it isn't there, as artifactr locks a workspace's. The row's `live` flag says whether the tenant exists, so a row can be locked before its tenant is created; a refused command's insert rolls back with the rest, and of two concurrent creations of one tenant, one succeeds and the other is refused.
- **The audit log's sequence is the database's,** an autoincrementing key. Numbers from concurrent transactions needn't commit in order, but a tenant's transactions, and the deployment's, run one at a time under their lock, so a tenant's entries are numbered in the order they commit, and paging by sequence number misses none.
- **A check is one query, and one more when a grant names a custom role.** The groups a subject is in are found by a subquery of the first.
- **`Storage.tenants()`** lists the live tenants for operators, the third read that spans tenants.

## Options considered

| Option | For | Against |
|---|---|---|
| **Seven tables, the rest with what they hold (chosen)** | No table without a reader or writer | The RFC's list arrives over three phases |
| All ten tables now | The RFC's list at once | Three empty tables, which phases 4 and 5 would reshape |
| **Typed columns for subjects and resources (chosen)** | Phase 4's user and principal tables can take foreign keys; short index entries; a query names what it filters | Six columns where two would do |
| Each model's JSON as its key | One rule for every kind, with no escaping | No foreign keys, entries that grow toward PostgreSQL's index-entry limit, and keys that change if a model's fields or their order do |
| **The deployment as `~deployment` (chosen)** | Every row has a key; constraints apply; no tenant id can collide with it | A reserved character in tenant ids |
| The deployment as `""` | No reserved character | `''` is what an unset setting can read as, so phase 6's policy could match the deployment's rows |
| A nullable tenant | No reserved id | No primary key on the deployment's rows, and nothing to lock |

## Consequences

- Easier: phase 4 adds the user and principal tables with foreign keys from these columns, phase 5 adds a table and a migration, and phase 6 has one row per tenant to scope.
- Harder: a tenant id can't be empty or have a `~`, which `create_tenant` refuses.
