# ADR-0014: An operator enters a tenant by granting themselves

**Status:** Accepted; its last owner amended below
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Amends [ADR-0009](0009-a-deployment-wide-operator-role.md).

## Context

Lattice RFC-0001 says an operator doesn't see inside a tenant's workspaces, but can grant themselves a role there, in the audit log. Under [ADR-0010](0010-commands-bounded-by-what-their-maker-holds.md)'s rules a grant needs `grantr:grant` on the resource and every action of the role, and an operator holds only `grantr:create_tenant` and `grantr:grant_operator`, on the deployment.

## Decision

- **An operator may grant themselves any role in an existing tenant.** `grant` sees that the grantee is the maker and that the maker holds `grantr:grant_operator`, and then skips the check of `grantr:grant` and the bound.
- **It makes them a member first,** if they aren't one, and both steps are in the tenant's audit log, made by the operator.
- **Anyone may give up a grant of their own,** with no check: revoking it takes access away from no one else.
- **A tenant keeps an owner:** revoking, removing or deleting the last grant of `owner` on a tenant is refused, so a tenant is never left unmanaged.

## Options considered

| Option | For | Against |
|---|---|---|
| **An operator's own grant, audited in the tenant (chosen)** | What the RFC says; the tenant's admins see who entered | One exception to the bound |
| Give `operator` every tenant action | No exception | Puts operators inside every tenant, which ADR-0009 rules out |
| Operators ask an owner | No exception | A tenant with no reachable owner can't be helped |

## Consequences

- Easier: an operator can step into a tenant to help, visibly, and leave by revoking their own grants.
- Harder: `grant` has two paths, and the contract test covers both.

## Amendment (2026-10-16): the last owner is a member who holds owner

"A tenant keeps an owner" counted grants of `owner`, and a grant to a group counts whoever is in the group, no one included. So once a group held the only other owner grant, a tenant could be left with no member who holds `owner`, and only an operator granting themselves a role could manage it again ([lattice #253](https://github.com/alexnodeland/lattice/issues/253)): `define_group` emptying the group, `remove_member` removing its only member, or `revoke` of the last owner grant a person held while an empty group held another.

- **An owner is a member who holds `owner` on the tenant,** by a grant of their own or through a group's. A change that would leave none, where there was one, is refused as `Invalid`, naming the last owners.
- **Every command that can take it checks it:** `revoke`, `remove_member`, `delete_group`, and now `define_group`, last, after the command's own checks and the bound, as before.
- **The exceptions stand.** Anyone may give up a grant of their own, unless it leaves no owner, as before; an operator granting themselves a role is not checked, so an operator can still bring a tenant that has no owner back under management. A tenant that has no owner already, as one left so before this amendment, is not held to it, so its other changes go on until an operator steps in.

| Option | For | Against |
|---|---|---|
| **Count the members who hold owner (chosen)** | What "never left unmanaged" means; one rule for every command | A command reads the owner grants' groups |
| Refuse an owner grant to a group | Grants stay countable | Takes away a way of sharing ownership that works |
| Keep counting grants, and check `define_group` too | Smallest change | An empty group's grant still counts, so `revoke` and `remove_member` still leave no owner |

Consequences: the access state machine's invariant is now that a member holds `owner`, through a group or not, and its model refuses what grantr refuses. Portalr's grants page still hides only the revoke of the last owner grant, so a refusal there comes from grantr, as `Invalid`.
