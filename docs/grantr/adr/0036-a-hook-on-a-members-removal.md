# ADR-0036: A hook on a member's removal

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

For [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md)'s open question 3 ([#361](https://github.com/alexnodeland/lattice/issues/361)): what another package does when grantr removes a member, as portalr deletes a person's analytics events in the tenant ([portalr ADR-0075](../../portalr/adr/0075-a-person-removed-from-a-tenant-has-their-events-there-deleted.md)).

## Context

- **`Grants.remove_member` removes a member from a tenant,** with their grants, groups and keys, and audits it. No other package learned of it.
- **portalr keeps a person's analytics events per tenant,** which should go when the person does.

## Decision

- **`Grants.on_member_removed(hook)`** registers a coroutine of `(tenant, member)`. Each is awaited in turn once the removal has committed, never inside its transaction, so a hook never sees, or holds, grantr's lock.
- **A hook can't undo or fail the removal.** One that raises is logged by its error's type, never its message, and the next one runs.
- **A hook that must not miss a removal keeps its own work owed,** as portalr's does: grantr calls each hook once and keeps nothing for it.
- A removal that is refused runs no hook.

## Options considered

- **An event in the audit log, read by each package:** it is durable, but every package would need its own cursor over grantr's log, and its own reading of each entry's type.
- **Hooks inside the transaction:** a slow or failing hook, such as a ClickHouse call, would hold up the removal or roll it back.

## Consequences

- If the process stops between the commit and a hook, that removal's hook doesn't run. portalr owes its deletion from inside the hook, so that window is only the time between the commit and the hook's first write.
- Deleting a whole tenant runs no member's hook.
