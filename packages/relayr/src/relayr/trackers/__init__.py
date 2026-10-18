"""The tracker connector (lattice RFC-0004): rules' runs file and change items in a task tracker.

It sits behind one port, [`Tracker`][relayr.trackers.Tracker], with adapters for Plane's
Community edition in `relayr.plane` and Vikunja in `relayr.vikunja`, and one in memory,
[`FakeTracker`][relayr.trackers.FakeTracker]. A function action writes through
[`Trackers.acting`][relayr.trackers.Trackers.acting], an agent through
[`TrackerCapability`][relayr.trackers.TrackerCapability]:

```python
trackers = Trackers(
    ledger,
    connect=plane(http),
    integration=relayr.plane.INTEGRATION,
    credentials=tenant_credentials,
    bindings={WorkspaceKey("acme", "ops"): TrackerBinding(project=OPS, labels=("lattice",))},
    allowlists={"ops:dead-letters": Allowlist(trackers=True)},
)


async def file_dead_letter(reaction: Reaction[Deps]) -> None:
    event = reaction.events[0].event
    assert isinstance(event, RunDeadLettered)
    actions = reaction.deps.trackers.acting(reaction)
    item = await actions.ensure_item(
        ItemDraft(title=f"{event.rule} failed", priority="high"), key=f"dead-letter/{event.rule}"
    )
    if not isinstance(item, Deleted):
        await actions.comment(item, f"<p>Retried {event.attempts} times.</p>")
```

Every write is made once, by a key the ledger claims before anything is sent.

What people change in a bound project comes back as `tracker:` events
(`relayr.trackers.events`), published by
[`TrackerFollowers`][relayr.trackers.TrackerFollowers], one per bound workspace, which poll the
project and diff what they find against the ledger; a webhook only makes one poll now
([`relayr.fastapi.tracker_router`][relayr.fastapi.tracker_router]):

```python
followers = TrackerFollowers(trackers, automation)
await followers.resume()  # every bound workspace; `followers.watch` is reflexr's on_open
app.include_router(tracker_router(followers))
```
"""

from relayr.trackers.actions import (
    CLAIM_TTL,
    CREDENTIALS_TTL,
    LOOP_CAP,
    LOOP_WINDOW,
    WRITING,
    Connect,
    Credentials,
    Deleted,
    TrackerActions,
    TrackerBinding,
    TrackerRefused,
    Trackers,
)
from relayr.trackers.budget import Budget
from relayr.trackers.capability import TrackerCapability
from relayr.trackers.fake import FakeConnection, FakeTracker
from relayr.trackers.followers import LOOK_BACK, TrackerFollowers, event_id
from relayr.trackers.port import (
    Comment,
    CommentKey,
    CommentRef,
    Cursor,
    Item,
    ItemDraft,
    ItemFields,
    ItemKey,
    ItemRef,
    NotFound,
    Nudge,
    Page,
    Priority,
    ProjectId,
    RateLimited,
    Refused,
    State,
    Tracker,
    TrackerCredentials,
    TrackerError,
    Unauthorized,
    Unavailable,
)

__all__ = [
    "CLAIM_TTL",
    "CREDENTIALS_TTL",
    "LOOK_BACK",
    "LOOP_CAP",
    "LOOP_WINDOW",
    "WRITING",
    "Budget",
    "Comment",
    "CommentKey",
    "CommentRef",
    "Connect",
    "Credentials",
    "Cursor",
    "Deleted",
    "FakeConnection",
    "FakeTracker",
    "Item",
    "ItemDraft",
    "ItemFields",
    "ItemKey",
    "ItemRef",
    "NotFound",
    "Nudge",
    "Page",
    "Priority",
    "ProjectId",
    "RateLimited",
    "Refused",
    "State",
    "Tracker",
    "TrackerActions",
    "TrackerBinding",
    "TrackerCapability",
    "TrackerCredentials",
    "TrackerError",
    "TrackerFollowers",
    "TrackerRefused",
    "Trackers",
    "Unauthorized",
    "Unavailable",
    "event_id",
]
