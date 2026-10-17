# Filing work in a task tracker

This guide lets a rule's run file items in a task tracker, comment on them and move them between states, each exactly once however often the run is retried. It is phase 1 of [lattice RFC-0004](../../rfcs/0004-relayr-and-task-trackers.md), the outbound half: changes people make in the tracker don't come back into reflexr yet. Plane's Community edition and Vikunja are supported, and the [architecture](../architecture.md#trackers) says how it works.

## Wire it in

Install the extra for your tracker, `relayr-ai[plane]` or `relayr-ai[vikunja]`. `Trackers` needs the ledger, the adapter, where each tenant's credentials come from, the tracker project each workspace files into, and each rule's allowlist:

```python
import httpx

from relayr.outbound import Allowlist
from relayr.plane import plane
from relayr.trackers import TrackerBinding, TrackerCredentials, Trackers

http = httpx.AsyncClient()  # shared by every workspace's adapter; close it at shutdown


async def credentials(tenant: str) -> TrackerCredentials:
    return TrackerCredentials(**settings.tracker_credentials[tenant])


trackers = Trackers(
    ledger,
    connect=plane(http),
    credentials=credentials,
    bindings={WorkspaceKey("acme", "ops"): TrackerBinding(project=OPS, labels=("lattice",))},
    allowlists={"ops:dead-letters": Allowlist(trackers=True)},
)
```

- **The ledger** is the same one the followers and `Outbound` use. Every key a run writes by is claimed there before the tracker is asked, in `relayr_tracker_items` on SQL.
- **Credentials** are the tracker's URL, an API key of the tenant's own tracker user, its webhooks' secret, and, on Plane, the tenant's workspace slug. They are asked for at most every five minutes, and again at once when the tracker refuses the key, so a rotated key is picked up without a restart. Keys never reach the ledger, logs or spans.
- **A binding** is the one project a workspace files into, with what its items have unless the rule says otherwise: a `state`, a `priority` and `labels`. A workspace with no binding files nothing.

Each tenant has its own tracker workspace (a Plane workspace, or a Vikunja top-level project) and its own tracker user, whose key reaches only that tenant's work.

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

States are `backlog`, `todo`, `started`, `done` and `cancelled`; priorities `none`, `low`, `medium`, `high` and `urgent`. Descriptions and comments are HTML, as both trackers keep them.

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
- **The claim comes first.** `ensure_item` claims its key in the ledger, then asks the tracker for an item the key filed, and only then creates one. A claim older than 30 seconds that never recorded an item is taken again, with another look first, so a run killed between creating the item and recording it makes one item. Every request takes 10 seconds at most.
- **What the tracker keeps.** Plane gets the key as `external_id`, and `lattice:<tenant>/<workspace>` as `external_source`, on every item, comment and label, and answers a second create with the first item. Vikunja has no external ids, so what lattice writes ends with a line, `lattice-key: lattice:<tenant>/<workspace>/<key>`, which people see.
- **A deleted item stays deleted.** An item filed before is read before it is returned. If a person deleted it, the key is marked, and `ensure_item` returns `Deleted` from then on, without asking the tracker; use a new key to file a new item. A closed or archived item is returned, for the rule to reopen if it will.
- **Edits are keyed.** `update` reads the item and sends only the fields that differ. The values it sets are recorded on the item's key first, for the reading side of phase 2 to tell relayr's changes from people's.

## Allowlists

A rule writes to its tracker only if its allowlist says `trackers=True` ([ADR-0034](../adr/0034-an-allowlist-for-the-tracker.md)). The default is false, and a rule without it gets `NotAllowed`.

## Retries and failures

| The tracker | The attempt |
|---|---|
| Is unavailable, or times out | Fails with `tracker_unavailable`, and is retried on reflexr's backoff |
| Is rate-limited (429) | Fails with `tracker_rate_limited`, and is retried: an attempt never sleeps |
| Holds a fresh claim on the key from another attempt | Fails with `tracker_claimed`, and is retried |
| Refuses a write as invalid, or about something missing | `TrackerRefused`: an agent's model may do otherwise; a function action's attempt is retried |
| Refuses the tenant's key, after asking for the credentials again | Fails the run for good, with `tracker_unauthorized` |

reflexr's retries are the outbox: nothing is queued in relayr, and a tracker that is down blocks only the runs that file.

## Running the tracker

The tracker's API key is the tenant's own user's, a member of the tenant's workspace and its bound projects only. Plane CE makes workspaces, users and keys only in its web app, so an operator makes them by hand; Vikunja's are scriptable. Vikunja's token needs these scopes: `tasks` (`create`, `read_one`, `read_all`, `update`), `projects` (`read_one`), `tasks_comments` (`create`, `read_all`), `labels` (`create`, `read_all`) and `tasks_labels` (`create`, `delete`); its tokens must expire.

stackr's recipes for both trackers, the provisioning checklist and `make tracker-check`, and the template's `tracker` question, are RFC-0004's phase 1 too, and come in a later pull request.

## Testing

`FakeTracker` is the tracker in memory: give `connect=fake.connect` to `Trackers`, and act in it as people do (`edit`, `reply`, `archive`, `delete`) or fail it as a tracker does (`fail`, `lose_next_created`). relayr's contract test runs every adapter against the same tests: the fake; Vikunja's exchanges, recorded from a live Vikunja and replayed, or a live one (`moon run relayr:vikunja-up`, then `moon run relayr:test-vikunja`; with `RELAYR_RECORD=1` the recordings are made again); and Plane's API as its source reads, since no Plane was run to record one ([ADR-0035](../adr/0035-what-phase-1-settled-of-the-trackers-unknowns.md)).
