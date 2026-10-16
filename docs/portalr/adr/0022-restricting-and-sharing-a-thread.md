# ADR-0022: Restricting and sharing a thread, from its menu

**Status:** Accepted, amended by [ADR-0036](0036-people-by-email.md)
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 says restricted threads and artifacts never reach the UI, because the server never sends them, and that sharing a thread is a grant through grantr's API, from the thread's menu. grantr's phase 5 built both. A restricted thread or artifact is seen only by those granted a role on it, and by those who hold `grantr:restrict` where it is; artifactr's `hidden` hook, which the test application wires, leaves it out of every read and stream. grantr's API restricts an item (`POST /restrictions`), grants and revokes a role on it (`POST /grants`, `POST /revocations`), and lists a workspace's grants and restrictions.

Changing who sees what is a workspace admin's: `grantr:grant`, `grantr:revoke` and `grantr:restrict`, which an editor holds none of. grantr asks them on the item; listing a workspace's grants asks `grantr:grant` on the workspace, and its restrictions `grantr:restrict` there, so someone granted them on one thread alone changes it without listing the workspace. Listing the tenant's members takes `grantr:add_member`, which a workspace's admin needn't hold. A grant's grantee must be a member of the tenant already. grantr names people by id, and holds nothing else about them.

A thread can be restricted while someone has it open. Their store still holds it, and nothing in artifactr's stream says it's hidden: the server stops sending its events, and refuses what they send to it.

## Decision

- **A thread's page asks grantr on the thread itself:** reading it (`artifactr:read_threads`), posting in it, and granting, revoking and restricting on it. The composer shows only where posting is allowed, so someone a restricted thread is shared with as a viewer reads it and doesn't post, though they edit the workspace: a restricted thread holds only the roles granted on it.
- **A thread restricted while it's open says so.** The page asks grantr again when the window regains focus, when the workspace's stream reconnects, and when a post is refused. If reading turns false while the store still holds the thread, the page shows "This isn't available to you any more" in place of the chat. A thread the server never sent is "Thread not found", as before.
- **A thread's menu, Thread actions, holds Share… and Restrict, or Lift restriction,** shown where grantr allows them on the thread. Restrict shows only where its state can be read, so it is never offered for a state the page can't show. A person who may do neither sees no menu. While a thread is restricted, those who may read that see it on its page.
- **The menu and its sharing are a subtree of their own,** under an error boundary, that reads with suspense what grantr allows: the workspace's grants where `grantr:grant` is allowed on the workspace, its restrictions where `grantr:restrict` is, and the tenant's members where `grantr:add_member` is. The page's loader reads them ahead, never failing for them. Someone granted on the thread alone shares it with the people they may list, and is told they can't see who holds a role.
- **Share… opens a dialog** that lists who holds a role on the thread, each with Revoke where grantr allows that, and shares it with a person, as viewer or editor. The people offered are those with a role in the workspace, and, for whoever may list them, the tenant's members, less those with a role on the thread already. They are named by grantr's id, since grantr has no other name for them. Focus starts at the person, so Enter never revokes, and returns to the menu's button. A refusal is said for the form, under its fields.
- **Only viewer and editor are offered,** though grantr would grant any role, a tenant's own among them. They are what sharing a thread means; the role sent is checked against them.
- **Every answer to a change of access, done or refused, has grantr's reads in the tenant read again** (`keys.grantr.tenant`): the checks, `/me`, and the grants, restrictions and members. A person's memberships, which no change on a thread touches, aren't.
- **grantr's changes go over its REST, through `createCommands`,** as reflexr's rule commands do (ADR-0020), each naming its tenant in `X-Tenant` as every read does. `refusal()`, which words one, is `client`'s, beside `Answer`.
- **ui gains three generic parts.** `Dialog`, Base UI's Dialog, and its class strings in one module, which the drawer's backdrop shares; it passes `initialFocus` and `finalFocus` through. `Menu`, a button and its actions, each with a label, `onSelect`, and whether it's disabled, as Restrict is while it's being done. `SelectField`, a labelled native select, which submits as a form's field. The app's `ThreadMenu` and `ShareDialog` are built on them and hold nothing of Base UI. The gallery shows the dialog open.
- **The app's own components are tested in Chromium,** as ui's are: its vitest has a project for its logic, without a browser, and one for its components.
- **The test application has a workspace admin,** dana, who administers `notes` and may not list acme's members. A test holds it to what the scenarios rely on: a restricted thread is hidden from an editor and grantr's check that they may read it turns false; a viewer's grant shows it, read only; revoking hides it again, and lifting the restriction shows it; an editor may neither restrict one nor list the grants; and a workspace's admin lists its grants and not the members.

## Options considered

| Option | For | Against |
|---|---|---|
| **The workspace's grantees, and the tenant's members for those who may list them (chosen)** | No change to grantr; the people offered work in the workspace already | A workspace's admin who may not list members shares only with people in the workspace |
| The tenant's members, for those who may list them, and a field for an id otherwise | Anyone in the tenant | An id typed by hand |
| A members read a workspace's admin holds | Anyone in the tenant, picked | A change to grantr's roles for one screen |
| **Viewer and editor (chosen)** | What sharing a thread is | A tenant's own roles aren't offered |
| Every role grantr has | Whatever the tenant defined | More than a share means, on one thread |
| **In the thread's menu, with the grantees in the dialog (chosen)** | As RFC-0002 has it; one place | A dialog to open to see who has access |
| An Access panel on the thread's page | Always in view | Space on every thread, for a few |
| **Ask grantr again on focus, a reconnect, and a refused post (chosen)** | Uses what grantr answers already; nothing new on the server | A restriction shows when one of those happens, not the moment it's made |
| A frame on artifactr's stream when an item a client has is hidden | At once | A change to artifactr's protocol, and a check per connection for every restriction |

## Consequences

- Easier: an artifact's page can take the same menu and dialog, and any page its ui `Menu`, `Dialog` and `SelectField`.
- Harder: people are named by grantr's id until something gives the UIs their names.
- Harder: someone who has a thread open when it's restricted keeps seeing what they had until the window regains focus, the stream reconnects, or they post; then they're told it isn't available to them any more. Its runs' live frames stop at once, as artifactr's stream stops them.
