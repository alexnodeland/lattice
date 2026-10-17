"""The `tracker:` events: what people change in a bound tracker project, as reflexr sees it.

Each type is declared under [`TrackerEvent`][relayr.trackers.events.TrackerEvent], whose
`event_namespace="tracker"` makes every type `tracker:<name>`, as relayr's bridged types are
`artifactr:<name>` (relayr ADR-0006). Every event carries the tracker it came from, so a rule is
written once for Plane and Vikunja. Give [`TRACKED`][relayr.trackers.events.TRACKED] to reflexr's
`Workspaces(events=...)`, and [`PUBLISHERS`][relayr.trackers.events.PUBLISHERS] to its
`publishers=`, which reserves the namespace to the followers' source:

```python
workspaces = Workspaces(
    storage,
    events=[*BRIDGED, *TRACKED, *app_events],
    publishers={"artifactr": [relayr.inbound.SOURCE], **PUBLISHERS},
)
```

The application must never resolve a client to `source:tracker` (reflexr ADR-0057).
"""

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Final, Literal

from pydantic import JsonValue

from reflexr import Event, SourceActor
from relayr.trackers.port import ItemKey, Priority, ProjectId, State

SOURCE: Final = SourceActor(name="tracker")
"""Who the tracker followers publish into reflexr as: the actor on every `tracker:` envelope."""

PUBLISHERS: Final[Mapping[str, tuple[SourceActor, ...]]] = MappingProxyType({"tracker": (SOURCE,)})
"""The `tracker` namespace reserved to the followers' source, for reflexr's `publishers=`."""

type Field = Literal["title", "description", "state", "priority", "labels", "assignees"]
"""What a change to an item names."""


class TrackerEvent(Event, abstract=True, event_namespace="tracker"):
    """The base of the `tracker:` types: the item each is about, in the tracker it came from."""

    tracker: str
    """The tracker, by its integration's name after `tracker:`: `plane` or `vikunja`."""

    project: ProjectId
    item_id: str
    """The tracker's id for the item."""

    number: int
    """The item's number in its project."""

    name: str
    """What people call it, as the tracker shows it: `OPS-12`."""

    link: str
    """The item's address in the tracker's web app."""

    key: ItemKey | None = None
    """The key lattice filed it by, if lattice did."""


class ItemCreated(TrackerEvent, name="item_created"):
    """An item appeared in the project, filed by someone other than relayr."""

    title: str
    description: str
    state: State
    priority: Priority
    labels: tuple[str, ...]
    assignees: tuple[str, ...]
    actor: str | None = None
    """The tracker's id for whoever filed it, if the tracker says."""


class ItemChanged(TrackerEvent, name="item_changed"):
    """A field of an item differs from when it was last read, by someone other than relayr.

    Changes are read, not delivered: two between reads are one, and one undone between reads is
    none.
    """

    field: Field
    old: JsonValue
    new: JsonValue
    actor: str | None = None
    """The tracker's id for whoever changed it, if the tracker says and relayr changed nothing
    on the item since it was last read."""


class ItemCommented(TrackerEvent, name="item_commented"):
    """Someone other than relayr commented on an item."""

    comment_id: str
    body: str
    """The comment's text, as HTML."""

    author: str | None = None
    """The tracker's id for whoever wrote it, if the tracker says."""


class ItemRemoved(TrackerEvent, name="item_removed"):
    """An item left the project's list: deleted, or on Plane archived."""

    deleted: bool | None = None
    """Whether it was deleted, rather than archived, when that is known: for an item lattice
    filed, which its key finds archived."""


TRACKED: tuple[type[TrackerEvent], ...] = (ItemCreated, ItemChanged, ItemCommented, ItemRemoved)
"""Every `tracker:` type: give them to reflexr's `Workspaces(events=...)`, with the application's
own, so the followers may publish them."""

type TrackerProjection = Callable[[TrackerEvent], Event | None]
"""Maps a `tracker:` event to the application's own event, or to None to publish nothing.

What it returns is published with the `tracker:` event's id; an exception dead-letters it.
"""
