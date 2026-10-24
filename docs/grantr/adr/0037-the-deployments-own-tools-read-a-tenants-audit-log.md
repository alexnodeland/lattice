# ADR-0037: The deployment's own tools read a tenant's audit log

**Status:** Accepted
**Date:** 2026-10-24
**Deciders:** Alex Nodeland

Supersedes [ADR-0036](0036-a-hook-on-a-members-removal.md), for [lattice #697](https://github.com/alexnodeland/lattice/issues/697) and [portalr ADR-0075](../../portalr/adr/0075-a-person-removed-from-a-tenant-has-their-events-there-deleted.md).

## Context

- **ADR-0036's hook is called once, and keeps nothing for a hook.** If the process stopped between a removal's commit and the hook's first write, that removal's work was never owed.
- **The audit log keeps every removal,** durably, in the order of its `seq` within a tenant.
- **Nothing in the repository used the hook but portalr,** and it had not been released.

## Decision

- **`Grants.served_audit(tenant, after_seq, limit, keep)` reads a tenant's audit entries,** for the deployment's own in-process tools, and checks no one, as `served_tenants` does: no surface reaches it.
- **A tool keeps its own high-water mark,** per tenant. A tenant's entries commit in the order of their `seq`; the deployment's don't, since two tenants commit at once.
- **`Grants.on_member_removed` is removed.** A tool that must act on a removal reads it from the log.

## Options considered

- **Keeping the hook beside the log:** a removal would be owed twice, and the hook would have no user.

## Consequences

- A tool acts on a change when it next reads the log, not as the change commits.
- A tool that starts late reads every entry from the start of a tenant's log, unless it is told where to begin.
