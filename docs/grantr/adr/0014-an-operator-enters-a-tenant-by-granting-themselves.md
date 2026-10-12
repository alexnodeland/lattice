# ADR-0014: An operator enters a tenant by granting themselves

**Status:** Accepted
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
