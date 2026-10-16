# ADR-0033: A tenant's creation, in the deployment's log

**Status:** Accepted
**Date:** 2026-10-16
**Deciders:** Alex Nodeland

Amends [ADR-0007](0007-an-append-only-audit-log.md), [ADR-0013](0013-transactions-by-tenant-and-one-audit-log.md) and [ADR-0026](0026-row-level-security-under-the-scoping.md).

## Context

Creating a tenant appended one entry, `tenant_created`, to the new tenant's own log. The deployment's log (`GET /audit`, read with `grantr:grant_operator`) held only the operators' grants and revocations, so an operator who created a tenant left no trace there: an operator is usually not a member of the tenant it creates, and so can't read the tenant's log either. Who created which tenant was not in any log an operator reads.

The creation runs in the new tenant's transaction, which writes the tenant's row, its owner's grants and its entry together or not at all. [ADR-0026](0026-row-level-security-under-the-scoping.md)'s policies keep that transaction to its own tenant's rows, and let it read the deployment's grants and group members and nothing else of the deployment's. It could not add a row to the deployment's log.

## Decision

- **A tenant's creation is also an entry in the deployment's log,** of a new type, `deployment_tenant_created`, whose event names the `tenant` and its `owner`, a user's id and never an email. The entry has no tenant (`None`, the deployment's) and `by` is who created it, `None` for the in-process tools. The tenant's own `tenant_created` entry is as it was, and `create_tenant` still returns it.
- **Both are written in the one transaction,** by the code both `create_tenant` and `provision_tenant` run to create a tenant, so a failure leaves neither and a repeated or refused creation records nothing. `provision_tenant` returns both entries, and none for a tenant that exists.
- **An operator's view needs no new grant.** The deployment's log is read with `grantr:grant_operator`, and only an operator may create a tenant, with `grantr:create_tenant`: the `operator` role holds both, no other built-in role holds either, and a custom role can hold no deployment action. Whoever can create tenants can read who did, and nobody else can. The log shows every tenant's id to every operator, which is what operators do: they list every tenant already.
- **A tenant's transaction may insert that one entry, by a policy (migration 0005):** `grantr_audit_tenant_creation`, `FOR INSERT` and nothing else. Its `WITH CHECK` pins `tenant_id = '~deployment'`; a named tenant (`lattice.tenant_id` reads empty, not null, on a pooled connection after a transaction, and an empty one must match no event); the `event_type` column to `deployment_tenant_created`, and the event's own `type` to the same; and the event's `tenant` to the transaction's own tenant, so a tenant's code records its own creation and no other tenant's.
- **Nothing else of the deployment's log is open to it.** There is no `SELECT`, `UPDATE` or `DELETE` policy, so the log stays unreadable, unchangeable and undeletable to the application's role. Because `INSERT ... RETURNING` reads the new row back through the read policy, the adapter asks the table's sequence for the entry's number first, and inserts without `RETURNING`, on PostgreSQL, for a row of another scope than the transaction's.
- **The deployment log is numbered in the order its entries commit.** A creation holds only its own tenant's lock, so without more, entry 10 (a creation) could commit after entry 11 (an operator's grant), and a reader that had seen 11 and paged `after_seq=11` would never see 10. Every writer of the deployment log's entries therefore takes one transaction-scoped advisory lock, on the audit table of the schema (row-level security does not apply to advisory locks), and holds it until it commits: a change to the deployment takes it as its transaction begins, and a creation takes it before it takes the entry's number from the sequence. **The lock order is fixed: the tenant's row lock, then the deployment log's lock.** A transaction that holds the log's lock waits for no tenant's lock, and the tenants' locks are each taken first and once, so two transactions never wait on each other's. Memory and SQLite serialize every change, and take no lock.
- **The updated table of what a transaction sees and writes under the policies** (ADR-0026's, as of 2026-10-16):

  | Rows | Read | Changed, deleted or added |
  |---|---|---|
  | Its tenant's | Yes | Yes, and only to stay its tenant's |
  | The deployment's grants and group members | Yes: a check reads the application's and operators' grants | No |
  | The deployment's audit entry of its own creation | No | Added, once the pinned shape holds; never changed or deleted |
  | The deployment's other rows: its audit log, keys, roles and groups | No | No |
  | Another tenant's | No | No |
  | Any, when the transaction names no tenant | No | No |

## Options considered

| Option | For | Against |
|---|---|---|
| **An insert-only policy for one entry, in the creation's transaction (chosen)** | Atomic; the deployment's log stays closed to the application's role but for one pinned insert | A policy that lets a tenant's transaction write to the deployment's log |
| A second transaction on the owner's engine | No policy change | Not atomic: a crash between the two leaves a tenant with no deployment entry, or the reverse |
| Create the tenant in a deployment transaction | One scope | The deployment's transaction would need to write every tenant's rows, a far wider policy |
| A subject setting (`lattice.subject`), checked by the policy against the entry's maker | Pins `by` too | The shared `TenantSession` in lattice-core and every library would set it; `by` can be `None`; and the entry's maker columns and body would still need to agree |
| Record it in telemetry only | Nothing to store | Retention and readers are the stack's, as ADR-0007 decided |

## Consequences

- Easier: an operator's view of the deployment's log shows who created which tenant, and portalr's admin can show it.
- Harder: **tenant-scoped code can forge the entry.** The policy pins the type and the tenant, but not who made it: code running in a tenant's transaction, such as a bug in grantr or a query it can be made to run, could add `deployment_tenant_created` entries for its own tenant, in any maker's name, and as many as it likes. The maker is in the entry twice, in the `actor_*` columns and in the body's `by`, and the policy pins neither, so they can disagree with each other too: the columns decide what a filtered read keeps, and the body what it shows. A test adds one with a maker of its choosing. It could not forge another tenant's, any other type, or read, change or delete one. The entry is a record of what grantr's code did, as every entry is, and not a proof against that code.
- Harder: the deployment's creations and operators' changes **serialize**: a creation waits for an operator's change in progress and the reverse. Both are rare, and short.
- Harder: **the shared sequence leaks gaps and a number's existence.** The deployment's entries share the table's sequence with every tenant's, so the log's numbers have gaps, as they did. A tenant's transaction can insert a row with a number of its choosing, and gets a unique violation if the number exists, or no row from `ON CONFLICT DO NOTHING`; it learns that the number is taken, and nothing of the row. `ON CONFLICT DO UPDATE` is refused by the read policy, and `COPY FROM` by PostgreSQL itself under row-level security. Tests show each.
- Harder: the body is `json`, not `jsonb`, so its duplicate keys are kept. The policy reads the event's `type` and `tenant` with `#>>`, which takes the last key of a duplicate, as pydantic does when it reads the entry, so the policy and the reader see the same event.
- Harder: the deployment's log has a gap in its meaning for tenants created before this change, which have no such entry; the tenant's own `tenant_created` entry says who created it.
- Harder: a reader of the sequence numbers sees one more number for every tenant created, between the tenant's entry and the next.
- To revisit: whether the adapter should insert it on the owner's engine when it can be made atomic with the tenant's transaction.
