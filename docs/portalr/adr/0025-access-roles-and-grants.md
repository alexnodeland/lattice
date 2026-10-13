# ADR-0025: Access: roles and grants, on grantr's catalog

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

ADR-0024 gave admin's Access its members, groups and keys. Roles and grants waited on two lists grantr's API didn't read: the actions a custom role may hold, and the roles each kind of resource may be granted. grantr's catalog read now answers both, at `GET /grantr/v1/catalog` ([grantr ADR-0031](../../grantr/adr/0031-the-catalog-read.md)):

- the built-in roles a tenant's admins grant, each with the kinds of resource it may be granted on;
- the actions a custom role may hold;
- the kinds a custom role may be granted on.

Each read takes the same action as its changes:

| Part | Its read and its changes | Revoking |
|---|---|---|
| Roles | `grantr:define_role` | |
| Grants | `grantr:grant` | `grantr:revoke` |

## Decision

- **Roles and Grants are parts of Access,** `/t/$tenant/access/roles` and `/grants`, beside members, groups and keys. Each is gated in `beforeLoad`, and reads in `loader`, as ADR-0024's are.
- **The catalog is the deployment's,** read once and kept (`staleTime` infinite), under a key no tenant's change stales.
- **Roles** lists the catalog's built-in roles, each with the kinds it may be granted on, and the tenant's custom roles, each with its actions.
  - A custom role is created under a name that is neither built in nor taken. Its actions are chosen from the catalog's, and it holds at least one.
  - Each custom role's row has "Change actions", which reads the roles afresh and starts from its actions. A change that takes any away is confirmed, naming them.
  - Deleting a custom role says that its grants go with it.
  - grantr replaces a role's actions whole: the last to save wins, as with a group's members.
- **Groups and Roles share one form,** admin's `DefineSet`: create under a free name, or change from a row, with a confirmation naming what a change takes out.
- **Grants** lists every grant in the tenant: its role, where, and to whom.
  - It lists them broadest first: the tenant's, then each workspace's, then their threads', artifacts' and rules'.
  - Membership is left out. grantr gives `member` by adding a member and takes it by removing one, so Members shows it.
  - Revoke shows where `grantr:revoke` is allowed, and is confirmed. grantr refuses revoking a tenant's last owner, and the dialog shows that refusal.
- **A role is granted** from the catalog's built-in roles and, where they may be read, the tenant's custom roles.
  - Each is offered only on the kinds it may be granted on: a custom role on the catalog's `custom_kinds`.
  - A grant on a workspace names it; a grant on an item also names the item.
  - It goes to a member or a group, chosen from the tenant's where either may be read, or typed as `kind:id` where neither may. A rule holds its own role and is never granted one here.
- **What grantr allows is asked on the tenant.** grantr checks `grant` and `revoke` on each grant's resource, and refuses a role whose actions the granter doesn't hold. The form and Revoke show where the tenant allows them, and a refusal on a narrower resource says so. This is the one place Access's "hide what they may not use" is approximate.
- **The scenarios** add, against the same application:
  - alice creates a custom role and deletes it;
  - she grants a service principal she made `viewer` on `notes`, and revokes it.

## Options considered

| Option | For | Against |
|---|---|---|
| **The catalog, read from grantr (chosen)** | One list, the one `grant` accepts; a contract test holds it | A read more |
| The lists written into portalr | No read | Drifts from grantr's roles |
| **Ask on the tenant, and show a refusal (chosen)** | One check per screen | A grant on a workspace the admin can't grant on is offered, then refused |
| Ask on each resource as it's typed | Exact | A check per keystroke |
| **Leave membership out of Grants (chosen)** | Grants shows what was granted; Members shows who belongs | A member's `member` is on another part |
| List every grant | Complete | A row per member, none of which may be revoked here |

## Consequences

- Easier: a custom role's actions follow grantr's catalog, with no list in portalr to keep.
- Harder: a role's actions, like a group's members, are last-writer-wins until grantr can refuse a change made against an older version.
