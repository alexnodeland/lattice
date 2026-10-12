# ADR-0024: Who sees a restricted item

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

Builds on [ADR-0003](0003-visible-to-the-workspace-unless-restricted.md) and amends [ADR-0015](0015-a-check-writes-nothing.md) and [ADR-0016](0016-the-sql-adapter.md).

## Context

ADR-0003 makes a thread or artifact visible to its workspace unless it is restricted, and a restricted one visible only to those granted a role on it, the workspace's admins, and the tenant's owners and admins. It names people by built-in role. A tenant's custom roles, the application's principal and the agent acting for no one need a rule too, and the flag needs a place to live and a command that sets it.

## Decision

- **On a restricted item, a grant around it holds only if its role holds `grantr:restrict`.** Grants on the item itself hold as ever. The built-in roles that hold it are the workspace's `admin` and the tenant's `owner` and `admin`, so ADR-0003's list follows, and a custom role follows the same rule: who may restrict an item sees it.
- **`hidden` is the check's rule over a workspace's restricted items:** each one on which the subject holds nothing. The application's own principal, holding `application`, sees everything, as relayr and reflexr act for the whole deployment; the agent acting for no one sees no restricted item.
- **`resources` follows the same rule,** so a listing of threads or artifacts leaves out those the subject can't see.
- **`Grants.restrict(tenant, on, restricted=..., by=...)`** sets or clears the flag, and needs `grantr:restrict` on the item. Only a thread or artifact is restricted, and a change that changes nothing is `Invalid`. It records `Restricted` or `Unrestricted`. `restrictions(tenant, workspace, by=...)` lists a workspace's restricted items, with `grantr:restrict` on it.
- **The flag is a row in `grantr_resources`,** keyed by the tenant and the item, which makes the item known to grantr ([ADR-0015](0015-a-check-writes-nothing.md)). A check on a thread or artifact reads it by primary key; `hidden` reads a workspace's by an index on the tenant, workspace and flag. Deleting a tenant deletes its rows.

## Options considered

| Option | For | Against |
|---|---|---|
| **Ancestor grants hold if their role may restrict (chosen)** | One rule for built-in and custom roles; who may lift a restriction already sees what it hides | A custom role with `grantr:restrict` sees every restricted item where it is granted |
| Name the built-in roles that see through | Exactly ADR-0003's words | A custom admin role is blind to what it restricts |
| The item's creator restricts it too (lattice RFC-0001's open question) | Whoever starts a private thread can close it | grantr doesn't know who created an item; an application can grant its creator a custom role holding `grantr:restrict` on it instead |
| A separate `see_restricted` action | Seeing and restricting apart | One more action for every catalog and matrix, with no request for it |

## Consequences

- Easier: the matrix says who sees restricted items, in the `grantr:restrict` column.
- Harder: a check on a thread or artifact reads one more row, by primary key.
