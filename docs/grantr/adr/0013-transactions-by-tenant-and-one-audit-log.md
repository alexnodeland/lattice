# ADR-0013: Transactions by tenant, and one audit log

**Status:** Accepted; amended by [ADR-0016](0016-the-sql-adapter.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

grantr's storage has an in-memory adapter now, and an SQL one in phase 3 that phase 6 puts under row-level security, with a second engine for the work that spans tenants. Lattice RFC-0001 sketches the SQL tables and says a check is one indexed query, but not how transactions are scoped or how the audit log is numbered.

## Decision

- **A transaction is in one tenant, or on the deployment:** `transaction(tenant)`, serialized with every other there. It is where phase 6 sets `lattice.tenant_id`.
- **Every read takes its tenant, but two:** `tenant_grants(user)` and `key(id)` span tenants, since they are asked before the tenant is known, and are only on `Storage`, so phase 6 can route them to the second engine.
- **`grants(tenant, to, on=)` answers for a grantee and the groups it is in,** on the resources given: the one query a check makes. `has(grant)` is the point lookup for membership and duplicates.
- **The audit log is one sequence for the deployment,** and each entry names its tenant, `None` for the operators. The storage stamps each entry's sequence number and time, and reads a tenant's entries in order, paged by sequence number.

## Options considered

| Option | For | Against |
|---|---|---|
| **One audit sequence for the deployment (chosen)** | One counter; operators' events fit in it | A tenant's sequence numbers have gaps |
| One audit sequence per tenant | Gapless numbers per tenant | Operators' events need a sequence of their own, and two counters to keep in step |

## Consequences

- Easier: phase 6 has one place per transaction to set the tenant, and one place for the reads that span tenants.
- Harder: readers page over gaps in a tenant's sequence numbers.
- To revisit: the deployment's grants and audit entries are in no tenant, and `create_tenant` and an operator's own grant read the deployment's grants inside a tenant's transaction. Phase 6's policy, `tenant_id = current_setting('lattice.tenant_id')`, would hide them, so it lets the deployment's rows through, or those reads move to the second engine.
