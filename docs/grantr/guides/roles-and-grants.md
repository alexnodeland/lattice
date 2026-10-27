# Roles and grants

A grant binds a role to a grantee on a resource, in a tenant. A grantee holds an action on a resource when a grant to it, or to a group it is in, names a role with that action on the resource or on one it is in: a thread, artifact or rule is in its workspace, and a workspace in its tenant ([ADR-0002](../adr/0002-grants-down-to-threads-and-artifacts.md)).

## The built-in roles

grantr builds its roles over the catalogs it is given, so a library's new action reaches the roles that should hold it without a change to grantr ([ADR-0011](../adr/0011-built-in-roles-over-the-catalogs.md)). Each holds, in short:

| Role | Granted on | For |
|---|---|---|
| `owner` | a tenant | whoever answers for a tenant: everything in it, deleting it included |
| `admin` | a tenant | everything the owner holds except deleting the tenant |
| `member` | a tenant | belonging to it; on its own, listing the workspaces the member can open |
| `admin` | a workspace | everything in the workspace, its grants and restricted items included |
| `editor` | a workspace, thread, artifact or rule | reading, and the commands that change threads, artifacts and runs; not installing, updating, archiving or replaying rules, which are the workspace admin's |
| `viewer` | a workspace, thread, artifact or rule | reading, and giving feedback |
| `operator` | the deployment | creating tenants and granting other operators; nothing inside a tenant until they grant themselves a role there ([ADR-0009](../adr/0009-a-deployment-wide-operator-role.md), [ADR-0014](../adr/0014-an-operator-enters-a-tenant-by-granting-themselves.md)) |
| `application` | the deployment | the application's own work in every tenant ([ADR-0019](../adr/0019-runtime-actions-and-the-application-role.md)) |
| `rule` | a workspace, held without a grant since ADR-0029 | a stored rule's runs, in its own workspace ([ADR-0020](../adr/0020-the-rule-role.md), [ADR-0029](../adr/0029-a-stored-rule-acts-as-itself-in-its-own-workspace.md)) |

An `editor` holds `artifactr:use_model`, which a turn their message starts asks as them to answer with the model the message names: any model the application offers. It is asked with the model's name in `Access.model`, which grantr does not scope by, since a model is not an item of a workspace; which models a tenant is offered is narrowed where the application lists them ([artifactr ADR-0097](../../artifactr/adr/0097-a-message-chooses-the-model-of-the-turn-it-starts.md)). A custom role without it still posts: the turn answers with the default model, and a notice says why.

The [architecture](../architecture.md#built-in-roles) lists each role's actions, and the [permission matrix](matrix.md) shows every role against every action of artifactr, reflexr and grantr.

### The application and its rules

Only the application's own principal holds `application`. That is the principal `Grants(application=...)` names. `Grants.bootstrap()` grants it the role as the application starts, and takes the role from any other holder. grantr never answers a key for that principal, and it can't be made a tenant's member, so no tenant can borrow it.

The role holds:

- the application's bookkeeping, every `open` and every read;
- the runner's records;
- what its code rules write in artifactr through relayr;
- as `RULE_INSTALLS`, installing, updating and archiving the stored rules relayr installs on behalf of people who may install them ([ADR-0025](../adr/0025-the-application-lists-tenants-and-workspaces-and-writes-for-code-rules.md), [ADR-0027](../adr/0027-the-application-installs-the-rules-people-accept.md)).

A stored rule acts as itself, a `RulePrincipal(workspace, rule)`. It holds `rule` in its own workspace with no grant. You can't grant it anything beyond its own workspace, nor any role that manages access. A grant made to it beyond its own workspace before that was refused counts for nothing. Since no grant gives a stored rule its role, revoking doesn't stop it: archiving it does ([ADR-0029](../adr/0029-a-stored-rule-acts-as-itself-in-its-own-workspace.md)).

## Granting

```python
from grantr import Resource, User

ALICE, BOB = User(id="alice"), User(id="bob")

await grants.add_member("acme", BOB, by=ALICE)
await grants.grant("acme", "viewer", on=Resource(kind="workspace", workspace="main"), to=BOB, by=ALICE)
await grants.grant(
    "acme", "editor", on=Resource(kind="artifact", workspace="main", id="plan"), to=BOB, by=ALICE
)
await grants.revoke("acme", "viewer", on=Resource(kind="workspace", workspace="main"), to=BOB, by=ALICE)
```

- **Only members are granted roles.** `add_member` makes a user or service principal a member; `remove_member` takes its grants, its places in groups and its keys with it.
- **No one gives more than they hold** ([ADR-0010](../adr/0010-commands-bounded-by-what-their-maker-holds.md)). Granting a role on a resource needs `grantr:grant` there, and every action the role holds there.
- **A tenant keeps an owner.** grantr refuses a change that would leave no member holding `owner`, by a grant of their own or through a group's: a `revoke`, a `remove_member`, a `delete_group`, or a `define_group` that empties the group holding it. An owner grant to an empty group makes no one an owner ([ADR-0014](../adr/0014-an-operator-enters-a-tenant-by-granting-themselves.md)'s amendment). Over the admin API, the refusal is the `invalid` one, as for any `Invalid`.

## Groups

A group is a tenant's named set of members, granted roles as a member is:

```python
from grantr import Group

team = Group(id="design")
await grants.define_group("acme", team, frozenset({BOB}), by=ALICE)
await grants.grant("acme", "editor", on=Resource(kind="workspace", workspace="main"), to=team, by=ALICE)
```

## Custom roles

A tenant can define its own roles, granted wherever `editor` can be. A custom role holds only actions a workspace's admin holds, and can't take a built-in role's name:

```python
from grantr import Role

triage = Role(name="triage", actions=frozenset({"reflexr:read_runs", "reflexr:cancel_run"}))
await grants.define_role("acme", triage, by=ALICE)
await grants.grant("acme", "triage", on=Resource(kind="workspace", workspace="ops"), to=BOB, by=ALICE)
```

## Reviewing who may do what

`grantr.testing.matrix(catalogs, roles)` prints every role against every action of the catalogs, a tenant's custom roles included, as a Markdown table. Commit it beside the application and review its diff whenever a library, a role or a catalog changes: stackr's template does, in `access.md`, with a test that fails when it is out of date (`make access-matrix` writes it).

```python
from artifactr.workspace import ACTIONS as ARTIFACTR
from reflexr.workspace import ACTIONS as REFLEXR

from grantr.testing import matrix

print(matrix([ARTIFACTR, REFLEXR], [triage]))
```
