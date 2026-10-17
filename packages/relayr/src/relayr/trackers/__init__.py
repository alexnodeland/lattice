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
"""

from relayr.trackers.actions import (
    CLAIM_TTL,
    CREDENTIALS_TTL,
    WRITING,
    Connect,
    Credentials,
    Deleted,
    TrackerActions,
    TrackerBinding,
    TrackerRefused,
    Trackers,
)
from relayr.trackers.capability import TrackerCapability
from relayr.trackers.fake import FakeConnection, FakeTracker
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
    "WRITING",
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
    "TrackerRefused",
    "Trackers",
    "Unauthorized",
    "Unavailable",
]
