# ADR-0022: Restricting and sharing a thread, from its menu

**Status:** Accepted
**Date:** 2026-10-12
**Deciders:** Alex Nodeland

## Context

lattice RFC-0002 says restricted threads and artifacts never reach the UI, because the server never sends them, and that sharing a thread is a grant through grantr's API, from the thread's menu. grantr's phase 5 built both. A restricted thread or artifact is seen only by those granted a role on it, and by those who hold `grantr:restrict` on its workspace; artifactr's `hidden` hook, which the test application wires, leaves it out of every read and stream. grantr's API restricts an item (`POST /restrictions`), grants and revokes a role on it (`POST /grants`, `POST /revocations`), and lists a workspace's grants and restrictions.

Changing who sees what is a workspace admin's, as are `grantr:grant`, `grantr:revoke` and `grantr:restrict`: an editor holds none of them. Listing the tenant's members takes `grantr:add_member`, which a workspace's admin needn't hold. A grant's grantee must be a member of the tenant already. grantr names people by id, and holds nothing else about them.

## Decision

- **A thread's menu, Thread actions, holds Share… and Restrict, or Lift restriction,** each shown where grantr allows it on the thread itself. A person who may do neither sees no menu. While a thread is restricted, those who may restrict it see that on its page.
- **Share… opens a dialog** that lists who holds a role on the thread, each with Revoke where grantr allows that, and shares it with a person, as viewer or editor. The people offered are those with a role in the workspace, and, for whoever may list them, the tenant's members, less those with a role on the thread already. They are named by grantr's id, since grantr has no other name for them.
- **Only viewer and editor are offered,** though grantr would grant any role, a tenant's own among them. They are what sharing a thread means, and a person granted more on one thread would hold more than a share gives.
- **The composer shows where grantr allows `artifactr:post_message` on the thread,** not on the workspace, so someone a restricted thread is shared with as a viewer reads it and doesn't post, though they edit the workspace: a restricted thread holds only the roles granted on it.
- **grantr's changes go over its REST, through `createCommands`,** as reflexr's rule commands do (ADR-0020), and each answer refreshes grantr's reads for the tenant.
- **ui has a generic `Dialog`,** Base UI's Dialog on `dialog.ts`'s classes: a backdrop on the scrim, the popup, its title, its description and its actions. The thread's menu and the sharing dialog are the app's, on ui's `Dialog` and `menu.ts`'s classes, and the app depends on Base UI for its menu. The gallery shows the dialog open.
- **A restricted thread never reaches the UI,** as before: the server leaves it out, and a thread page for one says "Thread not found".
- **A test holds the test application to it:** alice restricts a thread, bob, an editor, no longer reads it, a viewer's grant shows it to him again, and he may not post in it; and an editor may not restrict one.

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

## Consequences

- Easier: an artifact's page can take the same menu and dialog.
- Harder: people are named by grantr's id until something gives the UIs their names.
- Harder: a thread restricted while someone has it open stays in their store until they read the workspace again; its runs' live frames stop at once, as artifactr's stream stops them.
