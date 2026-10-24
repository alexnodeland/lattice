# ADR-0075: A person removed from a tenant has their events there deleted

**Status:** Accepted
**Date:** 2026-10-23
**Deciders:** Alex Nodeland

Settles [lattice RFC-0008](../../rfcs/0008-portalr-product-analytics.md)'s open question 3 ([#361](https://github.com/alexnodeland/lattice/issues/361)). It reads [grantr ADR-0037](../../grantr/adr/0037-the-deployments-own-tools-read-a-tenants-audit-log.md)'s audit log.

## Context

- **A person's events are deleted when they take back their yes,** in every tenant, by their keyed hash. The deletion is owed until it is done (RFC-0008, P5).
- **Removing a person from a tenant deleted nothing.** Their events there stayed until their own no, or an operator's delete.

## Decision

- **Removal from a tenant deletes that tenant's events of the person,** up to the moment of the removal (the owner's decision): `DELETE … WHERE distinct_id = <their hash> AND tenant_id = <the tenant> AND ts <= <removed at>`, a lightweight delete by portalr's writer. Their events in other tenants stay. Events after the removal stay too, should they be added back and say yes again.
- **The pass owes, and deletes.** The relay reads the removals from grantr's audit log (Amended, below).
  - A removal writes one row to `portalr_analytics_removals_owed`, per person and tenant, with when they were removed. The admin's removal never waits on ClickHouse.
  - The background pass every replica already runs, `Relay.settle_owed`, deletes each owed removal at least 30 seconds after it (`REMOVAL_GRACE`). By then a batch the relay accepted just before the removal has landed: ClickHouse gathers asynchronous inserts for up to a second. It is deleted with the rest, with no second delete needed.
  - The pass clears the row only if that is still the removal owed, and a deletion ClickHouse couldn't take stays owed for the next pass.
  - A key's principal records no events, so nothing is owed for one.
- **It isn't paced per person.** The person's own requests set off at most so many deletions an hour, which stops a person from flooding ClickHouse with mutations. A removal is an admin's grantr command, not the person's request, and its deletion is made by the background pass, which isn't paced for consent's deletions either: each pass takes at most 100 removals.
- **The cut-off is 5 seconds past the removal** (`REMOVAL_MARGIN`). An event is stamped by the replica that relayed it, and that replica's clock may run a little ahead of the one that removed the person. The cost is that a person added back and sharing again within those seconds has those few seconds of new events deleted too.
- **The table is the tables' owner's alone.** An admin removes another person, so the row is no person's own: it is written and read as the owner, and the role the application connects as is granted nothing on it. On PostgreSQL it has row-level security, with a policy that lets no row through, so a grant made by default, such as Supabase's to its public roles, reads nothing; the owner bypasses it. stackr's smoke test holds every table of the application's to a policy. It is portalr's second migration.
- **The template wires it** in `Portal.mount`, where the relay is made and given grantr. So it runs only where the portal, analytics and the application's database are configured.
- **Replays** ([ADR-0077](0077-session-replay-its-own-yes-masked-in-the-browser-and-checked-at-the-relay.md)) are deleted by the same removals, with the tenant's session in Umami.

## Options considered

- **Deleting only when a person has left every tenant:** their events would stay in a tenant they no longer belong to, read by its admins.
- **Deleting at once, without owing it:** a ClickHouse outage at the moment of removal would keep the events for good.

## Consequences

- A tenant's adoption no longer counts a person removed from it.
- A second removal from the same tenant, before the first is settled, owes up to the later moment.
- **Amended 2026-10-24 ([#697](https://github.com/alexnodeland/lattice/issues/697)): the audit log owes the removal, not a hook.** A removal whose process stopped between grantr's commit and the hook's write was never owed. So the relay registers no hook, and grantr's is removed ([grantr ADR-0037](../../grantr/adr/0037-the-deployments-own-tools-read-a-tenants-audit-log.md)). The background pass reads each tenant's `member_removed` entries after a stored mark, per tenant (`portalr_analytics_audit_cursor`, the tables' owner's alone), because only a tenant's entries commit in order of their `seq`. It owes each one up to the entry's time, and moves the mark after, so a pass that stops partway reads them again.
- **A removal is owed on the next pass,** about five minutes, with its grace counted from the entry. The first pass reads each tenant's log from its start, so it also deletes the events of people removed before this: up to their removal, as the decision says.
- A person's own no needs no grace period. The relay reads their answer again after each write, which waits for ClickHouse to take it. A batch that lands after the no is deleted then, with a deletion owed of its own.
- Deleting a whole tenant isn't a removal, so it deletes nothing here; that is the operator's to do.
