# ADR-0010: Commands bounded by what their maker holds

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

Lattice RFC-0001 gives `Grants` its reads and says that no one grants more than they hold, that operators are granted by operators and the first by `make operator`, and that grantr's admin router checks its callers with grantr's own actions. Phase 2's exit criteria need the commands that change access before the router exists, and leave open where the bound applies beyond a grant, what a member is, and how the first operator is made.

## Decision

- **`Grants` holds the commands,** each made `by` a subject and checked with grantr's own action on the resource it changes: tenants, members, groups, custom roles, grants, keys and operators. Phase 3's router calls them, as the libraries' surfaces call their workspaces.
- **The bound applies to every change that gives or takes access,** where it applies: a grant's or revocation's role on its resource; each grant a removed member loses; the grants a group carries, when its members change or it is deleted; and the grants a principal holds, when a key is issued to act as it or revoked. So a tenant admin can't make themselves an owner by joining a group, or mint or revoke a key for an owner's principal. A custom role holds only workspace-level actions, which everyone who may define one holds, so defining one is bounded by construction. [ADR-0014](0014-an-operator-enters-a-tenant-by-granting-themselves.md) adds an operator's own grant, giving up one's own grant, and keeping a tenant's last owner.
- **A member is whoever holds the `member` grant on the tenant.** `add_member` and `remove_member` are its only paths, and `grant` and `revoke` refuse it. Roles are granted only to members, groups hold only members, and removing a member takes its grants, its places in groups and its keys. A new tenant's owner is made a member and an owner.
- **The first operator is made by `first_operator(user)`,** refused once any operator exists, and audited with no maker. Other operators are granted and revoked by `grant_operator` and `revoke_operator`, which an operator calls; `grant` refuses the deployment.
- **Each command is one transaction:** its checks, its change and its audit entry. The maker's action is checked first, so a refusal says nothing about what exists, and a tenant that a maker holds an action in exists.

## Options considered

| Option | For | Against |
|---|---|---|
| **Commands on `Grants`, each bounded where it gives or takes access (chosen)** | One place enforces the rules, for the router, the template's `make` targets and tests | `Grants` is larger than the RFC's sketch of its reads |
| Commands only in phase 3's router | `Grants` stays read-only | The rules would live in a router, and the exit criteria couldn't be tested before it |
| The bound on `grant` alone, as the RFC words it | Fewer checks | Group membership and keys would each be a way around it |
| Membership as any grant in the tenant | No `member` role to manage | Revoking a user's last role would silently end their membership, and a member with no roles couldn't exist |

## Consequences

- Easier: the router in phase 3 is a thin surface, and `make tenant` and `make operator` call the same commands.
- Harder: a command that changes a group or a key checks every grant it affects.
