# Approvals, answered by the people grantr names

Before an agent's run, a code session or an outside client calls something a person must approve, lattice-core's enforcer asks an approval, and the call waits for an answer. grantr stores each approval in its tenant, decides who may answer it from its own members, groups and grants, and records each step in its audit log ([ADR-0038](../adr/0038-approvals-stored-per-tenant-answered-by-grantrs-subjects-groups-and-grants.md), [lattice RFC-0011](../../rfcs/0011-the-v0-3-platform-capabilities-approvals-secrets-egress-and-adapters.md)).

## The store

`Grants.approvals()` returns the store, lattice-core's `Approvals`, over the same storage as the grants. The application gives it to the enforcer as its `store`:

```python
from grantr.grants import Grants

grants = Grants(storage, catalogs=[...])
approvals = grants.approvals()

enforcer = Enforcer(registry, ..., approvals=policy, coverage=coverage, store=approvals, ...)
```

Whichever surface the person answers on answers through the same store. The first answer wins: the store settles an approval in its tenant's transaction, and every other answer is refused with the first, who gave it, where and when. An approved approval lets one call through.

An approval past its deadline takes no answer. `approvals.expire_due()` closes those, in every tenant: run it on a schedule, as often as the shortest deadline needs.

## Who may answer

The policy names who may answer each approval: a grantr action, subjects, groups, or the caller alone. grantr decides from what it keeps, never from the groups an answerer claims:

| The approval names | Who may answer |
|---|---|
| An action, such as `grantr:answer_approval` | Whoever holds it on the approval's workspace |
| Subjects | Each of them |
| Groups | Each member of each, by grantr's groups |
| A different approver | Any of the above but the person who asked |
| A confirmation | The one person who called, on portalr's confirm page alone |

Only a member of the approval's tenant answers. The subjects and groups an approval names are people. A service principal answers only by holding the action through a grant made to it, not to a group it is in, and never a confirmation.

## Delegating

`grantr:answer_approval` is the action a policy names for the people who may answer in a workspace. A tenant's owners and admins hold it, and a workspace's admins hold it there. To let someone else answer, grant it to them, as a custom role:

```python
await grants.define_role("acme", Role(name="approver", actions=frozenset({"grantr:answer_approval"})), by=alice)
await grants.grant("acme", "approver", on=Resource(kind="workspace", workspace="notes"), to=User(id="sam"), by=alice)
```

Revoking the grant ends it at once. A grant has no expiry yet, so a delegation lasts until it is revoked.

## In the audit log

Each approval leaves its steps in its tenant's log, where portalr's admin shows them:

| Event | Made by |
|---|---|
| `approval_asked`: the approval, its workspace, the capability and the caller | The person the call acts for, or no one |
| `approval_answered`: approved or denied, and where | Whoever answered |
| `approval_closed`: expired or withdrawn, and why | No one |

The call an approval lets through is the enforcer's to audit, as every call is.
