"""What the tracker connector did in a workspace: what runs filed, and how its follower is doing.

:func:`filed_in` and :func:`following_in` read the connector's ledger, its bindings and the
adapter its follower made, and nothing of the tracker's: a link is made from the tenant's
credentials, and opening it is the tracker's to allow. They check no one: relayr's routes and
its provider ask reflexr's ``authorize`` about the workspace first, as reflexr's own reads do.
"""

from collections.abc import Mapping
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from relayr.ledger import Snapshot, Tracked, TrackedKey, TrackerDeadLetter, WorkspaceKey
from relayr.trackers.actions import LOOP_CAP, LOOP_WINDOW, TrackerBinding, Trackers
from relayr.trackers.port import ItemRef, Tracker

__all__ = ["Filed", "FiledItem", "Following", "Reading", "Writes", "filed_in", "following_in"]


class FiledItem(BaseModel):
    """An item a run filed, and the chains that wrote to it."""

    model_config = ConfigDict(frozen=True)

    key: str
    """The key it was filed by."""

    project: str
    id: str
    """The tracker's id for the item."""

    number: int
    name: str
    """What people call it, as the tracker shows it: `OPS-12`."""

    link: str | None
    """Its address in the tracker's web app, or None if the workspace is bound to no tracker now."""

    deleted: bool
    """Whether a person deleted it: its key files nothing again."""

    chains: list[str]
    """The causal chains whose runs filed it or commented on it, the one that filed it first."""


class Filed(BaseModel):
    """What the runs of a workspace filed in its tracker."""

    model_config = ConfigDict(frozen=True)

    tracker: str
    """The tracker, by its integration's name after `tracker:`: `plane` or `vikunja`."""

    items: list[FiledItem]
    """The newest first, by their number."""


class Reading(BaseModel):
    """How far a workspace's tracker follower has read its project."""

    model_config = ConfigDict(frozen=True)

    project: str
    cursor_at: datetime | None
    """The tracker's `updated_at` of the last item it read; None if the project had none."""

    swept_at: datetime
    """When it last read the whole project."""

    read_at: datetime | None
    """When it last read the project at all; None until it reads again after an upgrade."""


class Writes(BaseModel):
    """relayr's recent writes to one item, which the cap on loops counts."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    name: str | None
    """What people call it, if the follower has read it."""

    link: str | None
    writes: int
    """How many writes relayr made to it within the cap's window."""


class Following(BaseModel):
    """How the tracker connector is doing in a workspace."""

    model_config = ConfigDict(frozen=True)

    tracker: str
    """The tracker, by its integration's name after `tracker:`: `plane` or `vikunja`."""

    integration: str
    """Its key among the application's integrations, which switches it per workspace."""

    binding: TrackerBinding | None
    """The project the workspace is bound to, with its defaults; None if it is bound to none."""

    reading: Reading | None
    """How far its follower has read; None if it never has."""

    filed: int
    """How many items its runs filed."""

    dead_letters: list[TrackerDeadLetter]
    """The changes its follower could not publish, by event id."""

    writes: list[Writes]
    """The items relayr wrote to within the cap's window, the most written first."""

    loop_cap: int = Field(description="How many writes to one item the cap allows in its window.")
    loop_window_seconds: int = Field(description="The cap's window, in seconds.")


async def _connection(trackers: Trackers, workspace: WorkspaceKey) -> Tracker | None:
    """The workspace's adapter, to link with; None if it is bound to nothing now.

    The one its follower made, if it made one, so no credentials are asked for.
    """
    if workspace not in trackers.bindings:
        return None
    return trackers.connected(workspace) or await trackers.connection(workspace)


async def filed_in(trackers: Trackers, workspace: WorkspaceKey) -> Filed:
    """Each item the workspace's runs filed in its tracker, with its link and its chains."""
    every = await trackers.ledger.every_tracked(workspace)
    tracker = await _connection(trackers, workspace)
    return Filed(
        tracker=trackers.integration.removeprefix("tracker:"), items=_items(every, tracker)
    )


async def following_in(trackers: Trackers, workspace: WorkspaceKey) -> Following:
    """The workspace's binding, how far its follower read, and what it couldn't publish."""
    ledger = trackers.ledger
    read = await ledger.tracker_following(workspace)
    every = await ledger.every_tracked(workspace)
    written = await ledger.tracker_writes(workspace, within=LOOP_WINDOW)
    snapshots = await ledger.snapshots(workspace, list(written))
    tracker = await _connection(trackers, workspace)
    return Following(
        tracker=trackers.integration.removeprefix("tracker:"),
        integration=trackers.integration,
        binding=trackers.bindings.get(workspace),
        reading=None
        if read is None
        else Reading(
            project=read.project,
            cursor_at=None if read.cursor is None else read.cursor[0],
            swept_at=read.swept_at,
            read_at=read.read_at,
        ),
        filed=sum(key.kind == "item" and t.ref is not None for key, t in every.items()),
        dead_letters=await ledger.tracker_dead_letters(workspace),
        writes=_writes(written, snapshots, tracker),
        loop_cap=LOOP_CAP,
        loop_window_seconds=int(LOOP_WINDOW.total_seconds()),
    )


def _writes(
    written: Mapping[str, int], snapshots: Mapping[str, Snapshot], tracker: Tracker | None
) -> list[Writes]:
    """Each item relayr wrote to, the most written first, named where its follower read it."""
    found: list[Writes] = []
    for item_id, count in sorted(written.items(), key=lambda each: -each[1]):
        snapshot = snapshots.get(item_id)
        ref = None if snapshot is None else ItemRef.model_validate(snapshot.item["ref"])
        found.append(
            Writes(
                item_id=item_id,
                name=None if ref is None else ref.name,
                link=None if ref is None or tracker is None else tracker.link(ref),
                writes=count,
            )
        )
    return found


def _items(every: Mapping[TrackedKey, Tracked], tracker: Tracker | None) -> list[FiledItem]:
    """The items filed, each with the chains of its claim and of the comments posted on it."""
    commented: dict[str, list[str]] = {}
    for key, tracked in every.items():
        if key.kind == "comment" and tracked.ref is not None:
            commented.setdefault(str(tracked.ref["item"]), []).append(tracked.correlation_id)
    items: list[FiledItem] = []
    for key, tracked in every.items():
        if key.kind != "item" or tracked.ref is None:
            continue
        ref = ItemRef.model_validate(tracked.ref)
        chains = [tracked.correlation_id, *commented.get(ref.id, ())]
        items.append(
            FiledItem(
                key=key.key,
                project=ref.project,
                id=ref.id,
                number=ref.number,
                name=ref.name,
                link=None if tracker is None else tracker.link(ref),
                deleted=tracked.deleted,
                chains=list(dict.fromkeys(chains)),
            )
        )
    return sorted(items, key=lambda item: -item.number)
