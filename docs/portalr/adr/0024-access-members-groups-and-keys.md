# ADR-0024: Access: members, groups and keys, each where grantr allows its read

**Status:** Accepted, amended by [ADR-0036](0036-people-by-email.md)
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

Roles and grants need lists grantr's API doesn't read: the actions a custom role may hold, and the roles each kind of resource may be granted. They wait on that decision, and land as 6b-ii. [ADR-0025](0025-access-roles-and-grants.md) records them, on grantr's catalog read.

## Decision

- **Access is a route of parts, `/t/$tenant/access/members`, `/groups` and `/keys`,** under a tab bar of those grantr allows. It asks grantr once per screen, on the tenant, about every action its parts take. A part shows only where its read is allowed. Access joins the rail only where one is, and opens on the first. A part opened by its address that isn't allowed is not found, and says so inside the tenant's frame, under Access's tabs: "There's no such part of Access here". A part whose read fails says so there too, with a way to read it again.
- **Each part's gate is in `beforeLoad`, and its reads are in `loader`,** as ADR-0023 settles who may open a tenant: the checks are read, and a part not allowed is not found, or Access's index redirected to its first part, before any part's read goes out. The screens read the checks live, through admin's `useAccess(tenant)`, which also gives `changed`, so a change shows at once.
- **Members** lists people first, then service principals.
  - Remove shows where `grantr:remove_member` is allowed, on everyone but the person signed in. Its dialog says what goes with a member: every role in the tenant and their places in groups, and, for a service principal, every key issued to it. Only service principals have keys.
  - A person is invited by email, through portalr's `/invites`. The answer says they are invited, and nothing more: grantr knows a person by Supabase Auth's id for them, a UUID, which is what Members lists for them, since nothing portalr reads maps an id to an email. A refused invite keeps the email typed.
  - A service principal is made by name, as grantr makes one: a member of the kind `service_principal`.
- **Groups** lists each group with its members, each with their kind beside their id, such as "ci (service principal)".
  - Create makes a group under a name not yet taken, and refuses one that is, rather than replace its members.
  - Each group's row has "Change members", which reads the groups afresh and starts from that group's members. A change that takes anyone out is confirmed first, in a `ConfirmDialog` naming who loses the group's grants.
  - Members are chosen from the tenant's, where reading them is allowed (`grantr:add_member`), and typed as `user:id` or `service_principal:id` otherwise, each checked before anything is sent.
  - grantr replaces a group's members whole, and has no version to compare: two admins changing one group at once, the last to save wins, and its members are what they chose. The fresh read narrows that window; it doesn't close it.
  - Deleting a group says that its grants go with it and its members keep theirs.
- **Keys** lists each key by its public id and its service principal, never its secret.
  - A key is issued to a service principal, chosen from the tenant's where they may be read, or named otherwise. Where they may be read and there are none, Issue isn't shown: Members is where one is added.
  - Its secret is shown once, in a read-only field with a copy button, from the screen's state alone: no query, cache or link holds it. Done clears it, as do leaving Keys and revoking that key.
  - Revoke shows where `grantr:revoke_key` is allowed.
- **Every change goes through `client`'s commands,** and then `changedAccess` reads grantr's answers in the tenant again, done or refused, as the app's sharing does. `orThrow` turns a refusal into the error a `ConfirmDialog` stays open to say.
- **`ui`'s `ItemTable`** shows items as a table from 640 pixels, the breakpoint the app's run lists use, each row named by its first cell, and as a list of cards below, each headed and named by its first cell, with its labels and its actions. Only one is shown, so only one is in the accessibility tree. With no items, it is an `EmptyState`. The app's `RunList` moves onto it in a follow-up.
- **`ui`'s `TabNav` and `CheckboxGroup`** are Access's tabs, the current one marked with `aria-current`, and the choice of a group's members, on Base UI's checkbox group.
- **The scenarios** each run again against the same application, with names made afresh:
  - alice invites someone and removes them;
  - she adds a service principal, issues it a key that is listed by its id alone, and revokes it;
  - she creates a group and deletes it;
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
| **Create for new names, Change members per row (chosen)** | A name taken is refused; a change starts from the group's members | Two ways in, rather than one form |
| One form that creates or replaces | One way in | Silently replaces a group's members under a name typed again |

## Consequences

- Easier: Roles and Grants join as parts beside these, once their lists are decided ([ADR-0025](0025-access-roles-and-grants.md)).
- Harder: a key not copied when issued is lost; issuing another is the remedy.
- Harder: a group's members are last-writer-wins until grantr can refuse a change made against an older version.
- Harder: people are listed by their UUID until portalr reads who an id is.
