# Restricted threads and artifacts

A thread or artifact is visible to everyone with a role in its workspace, unless it is restricted ([ADR-0003](../adr/0003-visible-to-the-workspace-unless-restricted.md)). A restricted one is visible only to those granted a role on it, and to those who may restrict it ([ADR-0024](../adr/0024-who-sees-a-restricted-item.md)).

## Restricting

Restricting needs `grantr:restrict` on the item, which a workspace's `admin` and a tenant's `owner` and `admin` hold:

```python
from grantr import Resource, User

ALICE, CAROL = User(id="alice"), User(id="carol")
offer = Resource(kind="thread", workspace="main", id="offer")

await grants.restrict("acme", offer, by=ALICE)
await grants.add_member("acme", CAROL, by=ALICE)
await grants.grant("acme", "editor", on=offer, to=CAROL, by=ALICE)  # Carol sees it

await grants.restrictions("acme", "main", by=ALICE)  # [offer]
await grants.restrict("acme", offer, restricted=False, by=ALICE)  # the workspace sees it again
```

Only a thread or artifact is restricted, and restricting one that is restricted already is `Invalid`. Each change is in the tenant's audit log, as `restricted` or `unrestricted`. The admin API has the same at `GET` and `POST /tenants/{tenant}/restrictions`.

grantr doesn't know whether an item exists: check that it does, with artifactr, before you restrict it.

## Who sees a restricted item

On a restricted item, a grant on its workspace or tenant counts only if its role holds `grantr:restrict`. A grant on the item itself counts as it does on any item. So:

| Who | Sees it |
|---|---|
| Someone granted a role on the item, or in a group that is | Yes |
| The workspace's `admin`, the tenant's `owner` and `admin`, and a custom role with `grantr:restrict` | Yes |
| A workspace's `editor` or `viewer` with nothing on the item | No |
| The application's own principal | Yes: it works for everyone |
| A stored rule, or a service principal with a key | Only if granted a role on the item |
| An agent's turn | As the person it acts for |

## How artifactr leaves them out

`Grants.hooks(subject_of).hidden` is artifactr's `hidden` hook, which its `Workspaces` holds ([artifactr ADR-0062](../../artifactr/adr/0062-restricted-items-left-out-of-every-read.md)). artifactr then leaves what it hides out of every read, on every surface:

- **A hidden item is missing.** Reading one, or a command that names one, answers `NotFound`, as for an item that doesn't exist, so ids can't be probed.
- **Listings and the log leave it out.** An artifact event from a hidden thread is kept, without the thread it came from, so a visible artifact's history stays whole.
- **An open subscription asks again** every `hidden_refresh` (30 seconds by default), so a newly restricted item can reach an open stream until then; commands are refused at once.
- **An agent's tools read as the person the turn acts for,** so a chat can't surface what its person may not see.
