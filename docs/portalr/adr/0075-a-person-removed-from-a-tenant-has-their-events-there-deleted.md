# ADR-0075: A person removed from a tenant has their events there deleted

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

Settles [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md)'s open question 3 ([#361](https://github.com/alexnodeland/lattice/issues/361)). It uses [grantr ADR-0036](../../grantr/adr/0036-a-hook-on-a-members-removal.md)'s hook.

## Context

- **A person's events are deleted when they take back their yes,** in every tenant, by their keyed hash. The deletion is owed until it is done (RFC-0008, P5).
- **Removing a person from a tenant deleted nothing.** Their events there stayed until their own no, or an operator's delete.

## Decision

- **Removal from a tenant deletes that tenant's events of the person,** up to the moment of the removal (the owner's decision): `DELETE … WHERE distinct_id = <their hash> AND tenant_id = <the tenant> AND ts <= <removed at>`, a lightweight delete by portalr's writer. Their events in other tenants stay. Events after the removal stay too, should they be added back and say yes again.
- **It is owed before it is tried.** The relay registers `Relay.member_removed` with grantr's hook.
  - The hook first owes the deletion: `portalr_analytics_removals_owed` gets one row per person and tenant, with when they were removed. Then it tries the deletion, and clears the row only if that is still the removal owed.
  - A deletion ClickHouse couldn't take is tried again by the background pass every replica already runs, `Relay.settle_owed`.
  - A key's principal records no events, so nothing is owed for one.
- **The table is the tables' owner's alone.** An admin removes another person, so the row is no person's own: it is written and read as the owner, and the role the application connects as is granted nothing on it. It is portalr's second migration.
- **The template wires it** in `Portal.mount`, where the relay is made. So it runs only where the portal, analytics and the application's database are configured.
- **Replays,** when they come (RFC-0008, P8), are deleted by the same hook.

## Options considered

- **Deleting only when a person has left every tenant:** their events would stay in a tenant they no longer belong to, read by its admins.
- **Deleting at once, without owing it:** a ClickHouse outage at the moment of removal would keep the events for good.

## Consequences

- A tenant's adoption no longer counts a person removed from it.
- A second removal from the same tenant, before the first is settled, owes up to the later moment.
- Deleting a whole tenant isn't a removal, so it deletes nothing here; that is the operator's to do.
