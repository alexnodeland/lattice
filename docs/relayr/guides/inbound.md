# Bridging artifactr into reflexr

This guide wires relayr's inbound adapter into an application that uses both libraries, so that what people and agents do in a workspace can fire rules. The [architecture](../architecture.md) says how it works.

## Install

relayr is distributed as `relayr-ai` and imported as `relayr`. Its ledger needs SQL in production: install `relayr-ai[postgres]`, or `relayr-ai[sqlite]`.

## Wire it in

The followers start from the libraries' `on_open` hook. Each `Workspaces` takes one, so compose `followers.watch` with any other, such as the feedback mirrors':

```python
import artifactr
import reflexr.workspace
from relayr.events import BRIDGED, Projections
from relayr.inbound import Followers
from relayr.sql import SqlLedger, migrate

await migrate(engine)  # relayr's tables, beside the libraries'


async def on_open(tenant_id: str, workspace_id: str) -> None:
    await mirrors.watch(tenant_id, workspace_id)
    await followers.watch(tenant_id, workspace_id)


collaboration = artifactr.Workspaces(artifactr_storage, authorize=..., on_open=on_open)
automation = reflexr.workspace.Workspaces(
    reflexr_storage,
    events=[*BRIDGED, *my_event_types],
    rules=my_rules,
    authorize=...,
    on_open=on_open,
)
followers = Followers(collaboration, automation, SqlLedger(engine), projections=Projections())

await followers.resume()  # at startup: every workspace the ledger knows
...
await followers.aclose()  # at shutdown: each follower releases its lease
```

- **`events` must include `BRIDGED`.** reflexr refuses a type its `Workspaces` doesn't accept, and the follower stops, logging an error, until the workspace is next opened. Nothing is skipped meanwhile.
- **Give each process its own `holder`,** or leave it to its random default. One process at a time follows a workspace; the others wait for its lease.
- **A workspace is followed from its first open**, and from startup once the ledger knows it.

## Write rules on bridged events

Bridged events are ordinary reflexr events in the `artifactr` namespace. Every one says who acted in artifactr, in which thread and turn:

```python
from reflexr import F, Rule, on, run
from relayr.events import MessagePosted

triage = Rule(
    name="ops:triage-mentions",
    when=on(MessagePosted).where(F.author.kind.eq("user")).where(F.content.contains("@oncall")),
    then=run("triage"),
)
```

The envelope's actor is `SourceActor("artifactr")` on every bridged event; `author` is who acted. Filtering on `F.author.kind` keeps a rule from reacting to agents, including its own writes once relayr's outbound adapter exists.

## Bridge your own events

`Projections` maps an `app_event`, by its name, or an artifact kind to the application's own event type, in its own namespace:

```python
import artifactr.core
from reflexr import Event


class Ops(Event, abstract=True, event_namespace="ops"): ...


class Deployed(Ops, name="deployed"):
    service: str


def deployed(envelope: artifactr.core.Envelope) -> Deployed:
    assert isinstance(envelope.event, artifactr.core.AppEvent)
    return Deployed.model_validate(envelope.event.data)


projections = Projections(app_events={"deploy": deployed})
```

- **An `app_event` with no projection stays in artifactr.**
- **An artifact kind's projection replaces the default set's** `artifact_created`, `artifact_changed` and `artifact_archived` for that kind. Proposals on it are still bridged as `artifactr:proposal_*`. Return None to bridge nothing.
- **Add the projected types to `events`,** as with `BRIDGED`.

## Dead letters

An envelope whose projection raises, an invalid event included, or returns one of reflexr's own events is dead-lettered, and its follower moves on:

```python
from relayr.ledger import WorkspaceKey

for letter in await ledger.dead_letters(WorkspaceKey("acme", "prod")):
    print(letter.seq, letter.event_type, letter.error)
```

Any other error, a type reflexr doesn't accept included, stops the follower and logs an error on `relayr.inbound`. It starts again, at its cursor, the next time the workspace is opened.

## Access

With access closed by an `authorize` hook, such as grantr's, the followers need four actions in every tenant ([ADR-0017](../adr/0017-the-follower-acts-as-the-application.md)):

| Library | Actor | Actions |
|---|---|---|
| artifactr | `SystemActor("relayr")` | `artifactr:open`, `artifactr:read_events` |
| reflexr | `SourceActor("artifactr")` | `reflexr:open`, `reflexr:publish` |

Map both to the application's own principal. Never resolve a client to `SourceActor("artifactr")`: rules trust it to mean relayr.

## Test it

Run the followers over both libraries' in-memory storage and an `InMemoryLedger`, and poll until reflexr's log has the events you expect, as relayr's own tests do:

```python
from relayr.ledger import InMemoryLedger

followers = Followers(collaboration, automation, InMemoryLedger())
```
