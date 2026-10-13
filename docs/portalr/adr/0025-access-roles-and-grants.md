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
  - A custom role is created under a name no custom role has; grantr refuses a built-in role's name, and the form shows that refusal. Its actions are chosen from the catalog's, grouped by library, and it holds at least one.
  - Each custom role's row has "Change actions", named "Change triager's actions", which reads the roles afresh and starts from its actions, and brings the form into view. A change that takes any away is confirmed, naming them.
  - An action the catalog no longer lists isn't offered: a change starts without it, and the confirmation names it as taken away.
  - The form says that an action added is added wherever the role is granted.
  - Deleting a custom role says that its grants go with it.
  - grantr replaces a role's actions whole: the last to save wins, as with a group's members.
- **Groups and Roles share one form,** admin's `DefineSet`: create under a free name, or change from a row, with a confirmation naming what a change takes out.
- **Grants** lists every grant in the tenant, a table per place, each under a visible heading that names it, "The tenant" or "Workspace notes": the tenant's, then each workspace's, its own before its threads', artifacts' and rules'.
  - Each row, or card, is named by whom, the role and where, such as "ops (group) as viewer on thread t_1 in notes".
  - Membership is left out. grantr gives `member` by adding a member and takes it by removing one, so Members shows it.
  - Revoke shows where `grantr:revoke` is allowed, and is confirmed. Its words are "Revoke", and its accessible name the whole grant, through `ConfirmDialog`'s `name`. grantr refuses revoking a tenant's last owner, and the dialog shows that refusal.
- **A role is granted** from the catalog's built-in roles and, where they may be read, the tenant's custom roles.
  - The form starts on no role and no one, each a required choice, so nothing is granted by a click. Choosing a role chooses where again.
  - Each role is offered only on the kinds it may be granted on: a custom role on the catalog's `custom_kinds`.
  - A grant on a workspace names it, from artifactr's workspaces as suggestions or typed; a grant on an item also names the item. Each is trimmed.
  - It goes to a member or a group, chosen from the tenant's where both may be read, or typed as `kind:id`, with what may be read suggested. A rule's role isn't offered here.
  - Granting owner or admin on the tenant is confirmed first, in a dialog naming whom it makes so: "Make olga admin of acme?".
  - What was entered stays after a refusal, which the form shows.
- **What grantr allows is asked on the tenant,** and that is exact for granting and revoking: a grant on the tenant holds on everything in it. grantr also refuses granting or revoking a role whose actions the granter doesn't hold where it is. Of the roles offered, only owner holds more than an admin, deleting the tenant among them. So owner is offered, and Revoke shown on its grants, only where `grantr:delete_tenant` is allowed.
- **The scenarios** add, against the same application:
  - alice creates a custom role and deletes it;
  - she grants a service principal she made `viewer` on `notes`, and revokes it.

## Options considered

| Option | For | Against |
|---|---|---|
| **The catalog, read from grantr (chosen)** | One list, the one `grant` accepts; a contract test holds it | A read more |
| The lists written into portalr | No read | Drifts from grantr's roles |
| **Offer owner only where deleting the tenant is allowed (chosen)** | Nothing offered that grantr refuses | One action more asked on each screen |
| Offer every role, and show grantr's refusal | No action more asked | Owner offered to every admin, and refused each time |
| **Leave membership out of Grants (chosen)** | Grants shows what was granted; Members shows who belongs | A member's `member` is on another part |
| List every grant | Complete | A row per member, none of which may be revoked here |

## Consequences

- Easier: a custom role's actions follow grantr's catalog, with no list in portalr to keep.
- Harder: a role's actions, like a group's members, are last-writer-wins until grantr can refuse a change made against an older version.
