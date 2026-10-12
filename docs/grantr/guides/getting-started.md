# Getting started

grantr answers one question, before every command and read: may this subject take this action on this resource, in this tenant? This page builds a deployment in memory, gives a person a role, asks grantr, and hands its hooks to artifactr. The [architecture](../architecture.md) says how each part works, and the [decision records](../adr/README.md) why.

## Install

grantr's core needs only pydantic. Its extras add the rest:

| Extra | For |
|---|---|
| `sql` | `SqlStorage`, with SQLAlchemy and Alembic, and a driver you install yourself |
| `postgres` | The same, with asyncpg |
| `sqlite` | The same, with aiosqlite |
| `fastapi` | `grantr_router`, the admin API |

```bash
uv add "grantr[postgres,fastapi]"
```

## A deployment, a tenant and a check

`Grants` holds grantr's checks and the commands that change access, over a storage. It is given each library's catalog, its `ACTIONS`, and builds its roles from them ([ADR-0011](../adr/0011-built-in-roles-over-the-catalogs.md)). Every command is made `by` a subject, and refused unless that subject may make it, and gives no more than it holds ([ADR-0010](../adr/0010-commands-bounded-by-what-their-maker-holds.md)).

```python
import asyncio

from artifactr.workspace import ACTIONS as ARTIFACTR
from reflexr.workspace import ACTIONS as REFLEXR

from grantr import Grants, InMemoryStorage, Resource, User

ROOT, ALICE, BOB = User(id="root"), User(id="alice"), User(id="bob")
MAIN = Resource(kind="workspace", workspace="main")
PLAN = Resource(kind="artifact", workspace="main", id="plan")


async def main() -> None:
    grants = Grants(InMemoryStorage(), catalogs=[ARTIFACTR, REFLEXR])

    # The deployment's first operator, who may create tenants.
    await grants.first_operator(ROOT.id)
    # A tenant, owned by Alice, who may then do anything in it.
    await grants.create_tenant("acme", owner=ALICE.id, by=ROOT)

    # Bob joins acme, and may edit what is in its main workspace.
    await grants.add_member("acme", BOB, by=ALICE)
    await grants.grant("acme", "editor", on=MAIN, to=BOB, by=ALICE)

    assert await grants.check("acme", BOB, "artifactr:edit_artifact", PLAN)
    assert not await grants.check("acme", BOB, "grantr:grant", MAIN), "an admin grants roles"
    assert not await grants.check("globex", BOB, "artifactr:read_artifacts", PLAN)

    # Every change is in the tenant's audit log.
    log = await grants.audit("acme", by=ALICE)
    assert [entry.event.type for entry in log][-2:] == ["member_added", "granted"]


asyncio.run(main())
```

A check refuses whatever no grant allows: an action in no catalog, a tenant the subject isn't in, a store that can't be read. Operators hold nothing inside a tenant until they grant themselves a role there, which the tenant's audit log records ([ADR-0014](../adr/0014-an-operator-enters-a-tenant-by-granting-themselves.md)).

## Asking from the libraries

artifactr and reflexr ask before every command and read through two hooks their `Workspaces` hold: `authorize`, which hears the action and the thread, artifact or rule it is about, and artifactr's `hidden`, which says what an actor may not see. `Grants.hooks(subject_of)` makes both, from the application's map of a library's actor to a grantr subject ([ADR-0012](../adr/0012-every-item-an-access-names-and-hooks-typed-by-actor.md)):

```python
from artifactr import core as artifactr
from artifactr.workspace import InMemoryStorage, Workspaces

from grantr import Agent, Subject, User


def subject_of(tenant: str, workspace: str | None, actor: artifactr.Actor) -> Subject:
    match actor:
        case artifactr.UserActor(id=user):
            return User(id=user)
        # An agent's turn is checked as the person it acts for (ADR-0004).
        case artifactr.AgentActor(on_behalf_of=artifactr.UserActor(id=user)):
            return User(id=user)
        case _:  # an actor this application doesn't know holds nothing
            return Agent()


hooks = grants.hooks(subject_of)
workspaces = Workspaces(InMemoryStorage(), authorize=hooks.authorize, hidden=hooks.hidden)
```

stackr's template does this for you, with a `subject_of` for each library that also maps keys, MCP clients, the application's own work and relayr's rules ([stackr ADR-0019](../../stackr/adr/0019-access-with-grantr-in-the-template.md)).

## In a database

`SqlStorage` keeps grantr in the application's database, beside the libraries' tables. Bring the schema up to date with `migrate` as the application starts:

```python
from sqlalchemy.ext.asyncio import create_async_engine

from grantr import Grants
from grantr.sql import SqlStorage, migrate

engine = create_async_engine("postgresql+asyncpg://app:secret@localhost/app")
await migrate(engine)
grants = Grants(SqlStorage(engine), catalogs=[ARTIFACTR, REFLEXR])
```

For SQLite, create the engine with `grantr.sql.create_sqlite_engine`. To have PostgreSQL keep tenants apart itself as well, see [row-level security](row-level-security.md).

## The admin API

`grantr_router` is the API a tenant's admins, and portalr, manage access through: tenants, members, groups, roles, grants, restrictions, keys and the audit log. The application says who each request comes from:

```python
from fastapi import FastAPI
from starlette.requests import HTTPConnection

from grantr.fastapi import Caller, Unauthorized, grantr_router


async def resolve_actor(connection: HTTPConnection) -> Caller:
    user = await verify_token(connection)  # the application's own sign-in
    if user is None:
        raise Unauthorized("no caller")
    return Caller(User(id=user))


app = FastAPI()
app.include_router(grantr_router(grants, resolve_actor=resolve_actor), prefix="/grantr/v1")
```

A key's caller names its one tenant, `Caller(principal, tenant)`, and the router holds every request to it. The routes, and how refusals look, are in the [architecture](../architecture.md#the-admin-api).

## Next

| To | Read |
|---|---|
| Choose roles, define your own, and review who may do what | [Roles and grants](roles-and-grants.md) |
| Keep a thread or artifact to some of a workspace's members | [Restricted threads and artifacts](restricted-items.md) |
| Give an integration a key | [Service principals and keys](keys.md) |
| Have PostgreSQL keep tenants apart under grantr | [Row-level security](row-level-security.md) |
