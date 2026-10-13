# ADR-0024: Access: members, groups and keys, each where grantr allows its read

**Status:** Accepted
**Date:** 2026-10-13
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 gives admin an Access area: members, invites, groups, roles (custom ones included), grants on workspaces, threads and artifacts, and service principals and their keys. grantr's API reads and changes each, and portalr's router invites someone through Supabase Auth and adds them to the tenant.

Each of grantr's reads takes the same action as its writes:

| Part | Its read and its changes | Removing and revoking |
|---|---|---|
| Members | `grantr:add_member` | `grantr:remove_member` |
| Groups | `grantr:manage_groups` | |
| Keys | `grantr:issue_key` | `grantr:revoke_key` |

The decisions ADR-0021 records hold here:

- destructive actions are in the danger colour, inside a `ConfirmDialog`;
- whatever a person may not use is hidden;
- on a phone, Access is a list of cards rather than a table scrolled sideways.

Roles and grants need lists grantr's API doesn't read: the actions a custom role may hold, and the roles each kind of resource may be granted. They wait on that decision, and land as 6b-ii.

## Decision

- **Access is a route of parts, `/t/$tenant/access/members`, `/groups` and `/keys`,** under a tab bar of those grantr allows. It asks grantr once per screen, on the tenant, about every action its parts take. A part shows only where its read is allowed. Access joins the rail only where one is, and opens on the first. A part opened by its address that isn't allowed is not found.
- **Members** lists people and service principals.
  - Remove shows where `grantr:remove_member` is allowed. Its dialog says what goes with a member: every role in the tenant, its places in groups, and its keys.
  - A person is invited by email, through portalr's `/invites`.
  - A service principal is made by name, as grantr makes one: a member of the kind `service_principal`.
- **Groups** lists each group with its members.
  - A group is made, or its members replaced, from the tenant's members, which takes reading them.
  - Deleting a group says that its grants go with it and its members keep theirs.
- **Keys** lists each key by its public id and its service principal, never its secret.
  - A key is issued to a service principal, chosen from the tenant's where they may be read, or named otherwise. Its secret is shown once, in a read-only field with a copy button, from the form's state alone: no query, cache or link holds it.
  - Revoke shows where `grantr:revoke_key` is allowed.
- **Every change goes through `client`'s commands,** and then `changedAccess` reads grantr's answers in the tenant again, done or refused, as the app's sharing does. `orThrow` turns a refusal into the error a `ConfirmDialog` stays open to say.
- **`ui`'s `ItemTable`** shows items as a table from 768 pixels, each row headed by its first column, and as a list of cards below, each with its labels and its actions. Only one is shown, so only one is in the accessibility tree.
- **The scenarios** each run again against the same application, with names made afresh:
  - alice invites someone and removes them;
  - she adds a service principal, issues it a key that is listed by its id alone, and revokes it;
  - she makes a group and deletes it;
  - on a phone, Members is a list of cards, with no table.

## Options considered

| Option | For | Against |
|---|---|---|
| **A route per part, under a tab bar (chosen)** | Each part reads and hides on its own; a link opens one | A click to reach another part |
| One page of every part | Everything at once | Every read on one screen, for a part the admin came for |
| **Show a key's secret once, from the form's state (chosen)** | Nothing keeps it after the person leaves | Lost if not copied then |
| Keep it in the query cache for the page | Survives a re-render | A secret held where every read is |
| **A table and a list of cards, one shown (chosen)** | Each fits its screen; one in the accessibility tree | Two renderings of each item |
| A table scrolled sideways | One rendering | ADR-0021 decided against it |

## Consequences

- Easier: Roles and Grants join as parts beside these, once their lists are decided.
- Harder: a key not copied when issued is lost; issuing another is the remedy.
