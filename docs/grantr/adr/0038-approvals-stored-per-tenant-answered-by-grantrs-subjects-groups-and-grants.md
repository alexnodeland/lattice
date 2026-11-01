# ADR-0038: Approvals stored per tenant, answered by grantr's subjects, groups and grants

**Status:** Accepted
**Date:** 2026-10-31
**Deciders:** Alex Nodeland
**Implements:** lattice [RFC-0011](../../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)'s T2 and T3, and lattice-core's `Approvals` port ([lattice ADR-0035](../../adr/0035-one-approval-per-call-bound-to-its-arguments-declared-in-lattice-core-and-stored-by-grantr.md)); beside [ADR-0034](0034-integrations-switched-per-tenant-and-workspace-in-grantrs-table-audited.md) and [ADR-0035](0035-settings-narrowed-per-tenant-and-workspace-in-grantrs-table-versioned-audited.md)

## Context

lattice RFC-0011 has one approval object for every ask a person answers before a call goes ahead, declared in lattice-core (`lattice_core.approvals`), and puts its store in grantr (T2): grantr's subjects decide who may answer, and it already keeps audited stores per tenant, with row-level security. A person delegates answering by a grantr grant, not by a field of the approval (T3).

The port asks for a compare-and-set: the first answer wins, the others are refused with it, and an approved approval lets exactly one call through (`take`, lattice [ADR-0037](../../adr/0037-the-enforcement-path-in-lattice-core-refusals-by-step-approvals-resumed-by-id.md)). Its methods take only an approval's id, while every grantr transaction is a tenant's.

## Decision

- **Table `grantr_approvals`** (migration 0008):
  - Columns: `tenant_id` and `id` (the primary key), `workspace`, `state`, and `approval`, the whole approval as JSON.
  - An index on `(tenant_id, state, workspace)` serves the reads of pending approvals.
  - The table has the row-level security policy every grantr table has.
- **An approval's id names its tenant:** `apr~<tenant>~<token>`, with a random 128-bit token. A tenant's id has no `~`, so the tenant is read back from the id, and each read and change runs as that tenant, under its policy. An id of another form, or one whose tenant has no such approval, is `UnknownApproval`.
- **`Grants.approvals()` returns `GrantrApprovals`,** lattice-core's `Approvals`:
  - Every change runs in its tenant's transaction, which every other change to the tenant waits on, with its audit entry.
  - `answer` reads the approval pending and settles it in that transaction, so the first answer wins on every storage. The others get `AlreadyAnswered`, carrying the first answer.
  - `take` does the same for an approved approval not yet taken.
- **Who may answer** is decided from grantr's own state; the groups an answerer claims count for nothing. A subject must be a member of the approval's tenant, and:
  - it is named in the approval, or is in a group the approval names, by grantr's groups;
  - or it holds the approval's action on the approval's workspace, by grantr's grants, as a check holds it;
  - never, where a different approver is asked, when it is the person who asked;
  - a confirmation is answered only by the one person it names, on `portalr:confirm`;
  - a service principal answers only by holding the action through a grant made to it, not to a group it is in: RFC-0011's "granted the action specifically". The subjects and groups an approval names are people, since a service principal's id may be a person's too, and a principal with a person's id must not answer as them. It never answers a confirmation.
- **A new action, `grantr:answer_approval`,** for the policy's `Answerers.action`. Tenant owners and admins hold it, and workspace admins hold it within their workspace. A person delegates answering by granting it, or a custom role that holds it, on a workspace (T3).
- **Three audit events:**
  - `approval_asked`: the approval, its workspace, its capability, and the caller as `kind:id`. It is made by the person the call acts for, or by no one.
  - `approval_answered`: whether it was approved, and where it was answered. It is made by the subject who answered.
  - `approval_closed`: expired or withdrawn, with the reason. It is made by no one.
  - Nothing, for taking an approval: the call it lets through is the enforcer's to audit.
- **Expiry:**
  - `expire_due()` is the sweep. It runs one transaction per tenant and expires every pending approval past its deadline.
  - An approval past its deadline takes no answer before the sweep reaches it, but stays pending until then.
- **Scoped answers are refused** (`ScopeNotOffered`): nothing offers a scope in 0.3.0. A plan's `covers` is stored with its approval, as every field is.
- **`watch`** reads the approval every `poll` (a second by default) until it is settled.

## Options considered

### Option A: The tenant in the id (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Low: one parse, and every read is a tenant's |
| Isolation | Row-level security holds every read and change |
| Port | Unchanged: the id is opaque to its callers |

**Pros:** no read spans tenants. A forged id names a tenant whose policy hides every other tenant's rows.
**Cons:** the id is longer, and shows its tenant to whoever holds it, who is in that tenant already.

### Option B: A lookup from id to tenant across tenants

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a read on the engine that bypasses the policies |
| Isolation | The lookup bypasses row-level security, like the key lookup does |

**Pros:** short, opaque ids.
**Cons:** one more read that bypasses row-level security, on a path every answer takes.

### Option C: The tenant as an argument of each method

**Cons:** it changes lattice-core's port, which every surface and the enforcer call by id alone.

## Trade-off analysis

The id that names its tenant keeps the port as RFC-0011 has it, and adds no read that bypasses row-level security. The tenant's own transaction is the compare-and-set: grantr already serializes a tenant's changes on its row's lock, on PostgreSQL and SQLite alike, so the race needs no new mechanism. Deciding who may answer from grantr's members, groups and grants, never from what the answerer claims, keeps delegation where access already lives (T3).

## Consequences

- Easier: one audited store for every approval, which any surface answers through the same port.
- Easier: a person delegates answering with a grant, and revoking it takes effect at once.
- Harder: an approval answered once can't be reused for another call. An approved approval is taken once, and a second call asks again.
- The surfaces aren't told yet: `ApprovalSurface`'s offer and resolution come with portalr's approvals.
- A grant has no expiry yet, so a delegation lasts until it is revoked. RFC-0011's "a grant with an expiry" is its own change.
- The list of a caller's approvals over MCP (lattice RFC-0014's `grantr:read_approvals`) comes with that tool.

## Action items

1. [x] The table, the store, the action and the audit events, tested on memory, SQLite and PostgreSQL with row-level security, with RFC-0011's race test.
2. [ ] Surfaces offered each approval and told of its resolution (portalr's approvals).
3. [ ] `admin_high` confirmation and the `admin-high:different-approver` setting.
4. [ ] artifactr's deferred approvals backed by this store.
