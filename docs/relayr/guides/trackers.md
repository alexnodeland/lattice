# Filing work in a task tracker

This guide lets a rule's run file items in a task tracker, comment on them and move them between states, each exactly once however often the run is retried; and brings what people change there back into reflexr as `tracker:` events, once each, for rules to react to. It is phases 1 and 2 of [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md). Plane's Community edition and Vikunja are supported, and the [architecture](../architecture.md#trackers) says how it works.

## Wire it in

Install the extra for your tracker, `relayr-ai[plane]` or `relayr-ai[vikunja]`. `Trackers` needs the ledger, the adapter, where each tenant's credentials come from, the tracker project each workspace files into, and each rule's allowlist:

```python
import httpx

from relayr.ledger import WorkspaceKey
from relayr.outbound import Allowlist
from relayr.plane import INTEGRATION, plane
from relayr.trackers import TrackerBinding, TrackerCredentials, Trackers

http = httpx.AsyncClient()  # shared by every workspace's adapter; close it at shutdown


async def credentials(tenant: str) -> TrackerCredentials:
    return TrackerCredentials(**settings.tracker_credentials[tenant])


trackers = Trackers(
    ledger,
    connect=plane(http),
    integration=INTEGRATION,  # "tracker:plane"
    credentials=credentials,
    bindings={WorkspaceKey("acme", "ops"): TrackerBinding(project=OPS, labels=("lattice",))},
    allowlists={"ops:dead-letters": Allowlist(trackers=True)},
)
```

- **The ledger** is the same one the followers and `Outbound` use. Every key a run writes by is claimed there before the tracker is asked, in `relayr_tracker_items` on SQL.
- **Credentials** are the tracker's URL, an API key of the tenant's own tracker user, its webhooks' secret, and, on Plane, the tenant's workspace slug. They are asked for at most every five minutes, and again at once when the tracker refuses the key, so a rotated key is picked up without a restart. Keys never reach the ledger, logs or spans.
- **A binding** is the one project a workspace files into and reads back, with what its items have unless the rule says otherwise: a `state`, a `priority` and `labels`. A workspace with no binding files nothing, and reads nothing.
- **The budget** is how many requests a minute each tenant's key may make from this process, 40 by default: runs' writes spend it first, and the followers' polls take what is left. Plane allows 60 a minute unless its `API_KEY_RATE_LIMIT` says more.

Each tenant has its own tracker workspace (a Plane workspace, or a Vikunja top-level project) and its own tracker user, whose key reaches only that tenant's work.

## Switching it per workspace

Each tracker is an integration of its own, by its key: `tracker:plane` or `tracker:vikunja`. Give `Trackers` the application's `integrations`, lattice-core's `Integrations` port, whose `is_enabled(tenant_id, workspace_id, key)` says whether the tracker runs in a workspace, and every action and tool asks it first; one switched off is `NotAllowed`, before the ledger or the tracker is touched. The followers and the webhooks' route ask it too: a switched-off workspace's follower polls nothing and lets its lease go, and its webhooks are refused. Without one, the tracker runs in every bound workspace ([`relayr.integrations.ALWAYS`](../reference.md)).

grantr's `Grants` is the port, whose switches are kept per deployment, tenant and workspace, audited, and set from portalr's admin ([grantr's guide](../../grantr/guides/integrations.md)).

```python
trackers = Trackers(
    ledger, connect=plane(http), integration=INTEGRATION, integrations=grants, ...
)
```

## From a function action

`trackers.acting(reaction)` is what the attempt may do in the tracker:

```python
from reflexr.core import RunDeadLettered
from relayr.trackers import Deleted, ItemDraft


async def file_dead_letter(reaction: Reaction[Deps]) -> None:
    event = reaction.events[0].event
    assert isinstance(event, RunDeadLettered)
    actions = reaction.deps.trackers.acting(reaction)
    item = await actions.ensure_item(
        ItemDraft(title=f"{event.rule} failed", priority="high", labels=("run-failed",)),
        key=f"dead-letter/{event.rule}",
    )
    if isinstance(item, Deleted):
        return  # a person deleted it: don't file it again
    await actions.comment(item, f"<p>Retried {event.attempts} times: {event.reason}</p>")
    await actions.set_state(item, "todo")
```

| Method | Does |
|---|---|
| `ensure_item(draft, key=...)` | Files an item, or returns the one its key filed; `Deleted` if a person deleted it |
| `comment(item, body, key=...)` | Posts a comment, once |
| `set_state(item, state)` | Moves an item lattice filed to a state, unless it is there |
| `update(item, fields)` | Sets the fields given on an item lattice filed, sending only those that differ |
| `read(item)` | Reads an item's snapshot, archived or not; None if it was deleted |
| `filed(key)` | The item a key filed, if it is still there |
| `link(item)` | The item's address in the tracker's web app |

States are `backlog`, `todo`, `started`, `done` and `cancelled`; priorities `none`, `low`, `medium`, `high` and `urgent`. Descriptions and comments are HTML, as both trackers keep them. Vikunja has only a `done` flag: `done` and `cancelled` set it, the others clear it, and it reads back as `done` or `todo`.

## From an agent

Add `TrackerCapability` beside reflexr's `EventContext`:

```python
from relayr.trackers import TrackerCapability

agent = Agent(model, deps_type=Reaction[Deps], capabilities=[
    EventContext(),
    TrackerCapability(trackers),
])
```

Its tools are `file_item`, `comment_on_item`, `set_item_state` and `read_item`. The agent names each item by a key it chooses, such as `incident/<id>`: filing by a key used before finds that item. What the allowlist refuses, or the tracker refuses as invalid or missing, comes back to the model as a retry.

## Keys, and writing once

Neither tracker deduplicates a retried request, so relayr does.

- **A key per write.** An item is filed by the key the rule gives, or one derived from the run and the draft, as `Outbound` derives its ids. A key of the rule's own, such as `dead-letter/<rule>`, files later runs into the same item; a derived one gives each run its own.
- **The claim comes first.** `ensure_item` claims its key in the ledger, then asks the tracker for an item the key filed, and only then creates one. A claim older than 30 seconds that never recorded an item is taken again, with another look first, so a run killed between creating the item and recording it makes one item; an item found that way is given the draft's labels, which Vikunja adds after it makes the task. The writes under a claim take 20 seconds at most, all told. A write the tracker refused releases the claim, so the run can write by the key again at once.
- **What the tracker keeps.** Plane gets the key as `external_id`, and `lattice:<tenant>/<workspace>` as `external_source`, on every item, comment and label, and answers a second create with the first item. Vikunja has no external ids, so what lattice writes ends with a line, `lattice-key: lattice:<tenant>/<workspace>/<key>`, which people see.
- **A deleted item stays deleted.** An item filed before is read before it is returned. If a person deleted it, the key is marked, and `ensure_item` returns `Deleted` from then on, without asking the tracker; use a new key to file a new item. A closed or archived item is returned, for the rule to reopen if it will.
- **Edits are keyed.** `update` reads the item and sends only the fields that differ, as the tracker will hold them. The values it sets, and those an item is filed with, are recorded on the item's key first, so the followers tell relayr's changes from people's.
- **A cap on loops.** relayr makes at most 20 writes to one item an hour, counted in the ledger; the next fails its run for good, as `tracker_loop`, and is counted in `relayr.trackers.loops`.

## Reading back

A follower per bound workspace polls its project, compares what it finds with what the ledger last read, and publishes what people changed into the workspace, as `SourceActor(name="tracker")`. Wire it beside `Trackers`:

```python
from relayr.fastapi import tracker_router
from relayr.inbound import SOURCE
from relayr.trackers import TrackerFollowers
from relayr.trackers.events import PUBLISHERS, TRACKED

automation = Workspaces(
    storage,
    events=[*BRIDGED, *TRACKED, *my_event_types],
    publishers={"artifactr": [SOURCE], **PUBLISHERS},
    on_open=on_open,  # composed with followers.watch, as the bridge's followers are
)
followers = TrackerFollowers(trackers, automation)
await followers.resume()  # at startup: every bound workspace, opened or not
app.include_router(tracker_router(followers))  # POST /relayr/v1/trackers/{tenant}/{tracker}
...
await followers.aclose()
```

| Event | When | Carries |
|---|---|---|
| `tracker:item_created` | An item appears that relayr didn't file | Its title, description, state, priority, labels and assignees; `actor` if the tracker names one |
| `tracker:item_changed` | A field differs from when the item was last read | `field`, `old`, `new`; `actor` if the tracker names one and relayr changed nothing on the item meanwhile |
| `tracker:item_commented` | Someone other than relayr commented | The comment's id, its text as HTML, and its `author` |
| `tracker:item_removed` | The item left the project's list | `deleted`, when known: for an item lattice filed, its key tells deleted from archived |

Every event carries `tracker` (`plane` or `vikunja`), the project, and the item's id, number, name, link and `key`, if lattice filed it, so a rule is written once for both trackers:

```python
reflexr.Rule(
    name="ops:postmortem",
    when=reflexr.on(ItemChanged).where(field="state", new="done"),
    then=reflexr.run("propose_postmortem"),
)
```

- **Polls, not webhooks.** A follower polls every 30 seconds, from two minutes before where it read to, so a change committed late is still found. A webhook only makes it poll now, debounced by two seconds; one lost costs latency, never a change. A change no webhook announced is counted in `relayr.trackers.unnudged`, so a webhook Plane switched off shows.
- **Level-triggered.** Each poll publishes one event per field that differs: two changes between polls are one, and one undone is none. Comments are read when an item changes, which a comment does on both trackers.
- **Once, by derived ids.** Every event's id is a digest of what it says, so a page read again, by another replica or after a restart, publishes nothing new. A relayr stopped for hours loses no change: it reads them when it starts.
- **A new binding is quiet.** Its first read publishes nothing; give the binding a `since` to publish the items changed since then as created.
- **Removals, daily.** Once a day the follower reads the whole project, and publishes `tracker:item_removed` for what left it. Plane sends no webhook when a work item is deleted, so this is the only way a deletion is found. An item lattice filed and a person deleted is never filed again.
- **relayr's own changes are dropped,** by the values it recorded before writing them; what is left is a person's. A person's change on an item a run filed joins that run's chain, without going deeper, so depth never grows through a tracker, and the cap on writes ends a loop the filter can't see.
- **Your own events.** `TrackerFollowers(projections={workspace: project})` maps a workspace's `tracker:` events to the application's, or to None; the event keeps the derived id. One that raises is dead-lettered, once per id, in `relayr_tracker_dead_letters` on SQL; a type reflexr refuses stops the follower until its workspace is next opened.
- **Untrusted text.** Titles, descriptions and comments are written by whoever can reach the tracker, and reach rules and their agents as chat messages do. Give agents' requests the gateway's `prompt-injection` guardrail.

The route is unauthenticated, and gives nothing away: a body over 1 MB is refused before more of it is read, a signature is checked first, with the secret the tenant's followers already hold, and an unknown tenant and a bad signature are the same 401, counted in `relayr.trackers.nudges_refused`. A nudge that reaches a replica not holding the binding's lease waits for the holder's next poll.

## In the portal

portalr shows, on each rule's run, the items its chain filed, with their links, and admin how the connector is doing in each workspace. Mount the connector's reads beside the webhooks' route, with the `resolve_actor` reflexr's router takes, and tell portalr where they are:

```python
from relayr.fastapi import tracker_reads_router

app.include_router(tracker_reads_router(trackers, workspaces, resolve_actor=resolve_reflexr_actor))
site = Site(supabase_url=..., supabase_key=..., surfaces=Surfaces(relayr=""))  # its paths carry /relayr/v1
```

Each read asks reflexr's `authorize`: what runs filed as `reflexr:read_runs`, how the follower is doing as `reflexr:read_dead_letters` ([ADR-0039](../adr/0039-the-tracker-connectors-reads-for-the-portal.md)).

## Allowlists

A rule writes to its tracker only if its allowlist says `trackers=True` ([ADR-0034](../adr/0034-an-allowlist-for-the-tracker.md)). The default is false, and a rule without it gets `NotAllowed`.

## Retries and failures

| The tracker | The attempt |
|---|---|
| Is unavailable, or times out | Fails with `tracker_unavailable`, and is retried on reflexr's backoff |
| Is rate-limited (429) | Fails with `tracker_rate_limited`, and is retried: an attempt never sleeps |
| Holds a fresh claim on the key from another attempt | Fails with `tracker_claimed`, and is retried |
| Takes longer than 20 seconds over one claim's writes | Fails with `tracker_unavailable`, and is retried; the claim holds its 30 seconds |
| Refuses a write as invalid, or about something missing | `TrackerRefused`: an agent's model may do otherwise; a function action's attempt is retried |
| Refuses the tenant's key, after asking for the credentials again | Fails the run for good, with `tracker_unauthorized` |
| Has taken 20 writes from relayr to the item within the hour | Fails the run for good, with `tracker_loop` |

reflexr's retries are the outbox: nothing is queued in relayr, and a tracker that is down blocks only the runs that file.

## Running the tracker

The tracker's API key is the tenant's own user's, a member of the tenant's workspace and its bound projects only. Plane CE makes workspaces, users and keys only in its web app, so an operator makes them by hand; Vikunja's are scriptable. Vikunja's token needs these scopes: `tasks` (`create`, `read_one`, `read_all`, `update`), `tasks_comments` (`create`, `read_all`), `labels` (`create`, `read_all`) and `tasks_labels` (`create`, `delete`); its tokens must expire.

Register the webhook to `POST /relayr/v1/trackers/<tenant>/plane` (or `/vikunja`) for work items and comments, signed with the tenant's webhook secret. stackr's recipes for both trackers, the provisioning checklist and `make tracker-check`, which needs three more scopes to read with, and the template's `tracker` question are in [stackr's tracker guide](../../stackr/guides/trackers.md).

## Testing

`FakeTracker` is the tracker in memory: give `connect=fake.connect` to `Trackers`, and act in it as people do (`edit`, `reply`, `archive`, `delete`) or fail it as a tracker does (`fail`, `lose_next_created`). relayr's contract test runs every adapter against the same tests: the fake; Vikunja's exchanges, recorded from a live Vikunja and replayed, or a live one (`moon run relayr:vikunja-up`, then `moon run relayr:test-vikunja`; with `RELAYR_RECORD=1` the recordings are made again); and Plane's, recorded from a live Plane v1.4.2 and replayed, or a live one (`RELAYR_TEST_PLANE_URL`), which signs up a user of its own ([ADR-0037](../adr/0037-what-a-live-plane-settled.md)). The same contract runs a follower over each. `TrackerFollowers.poll(tenant, workspace)` reads a project once, as the follower does each interval, so a test can drive it by hand.
