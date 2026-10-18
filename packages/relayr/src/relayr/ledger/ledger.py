"""The ledger port: relayr's own storage, beside the libraries'.

For each followed workspace it keeps a cursor, the lease that lets one follower at a time follow
it, and the envelopes the follower could not bridge. For the outbound adapter it keeps what
caused each of its writes in artifactr: the reflexr run, so the follower continues its chain.
For the tracker connector it keeps each key a run writes to the tracker by: the claim made before
the write, the item or comment it made, and the values relayr last set on an item. And for each
workspace bound to a tracker project it keeps what its tracker follower read: its lease and
cursor, the last snapshot of every item, relayr's recent writes to each, and the changes it could
not publish.
Every adapter passes the one contract test, `tests/ledger/test_contract.py`.
"""

from collections.abc import Callable, Collection, Mapping
from datetime import UTC, datetime, timedelta
from typing import Literal, NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict, JsonValue

Clock = Callable[[], datetime]
"""Returns the current time, which leases expire by; injectable so tests control it."""


def utc_now() -> datetime:
    """The system clock, in UTC."""
    return datetime.now(UTC)


class WorkspaceKey(NamedTuple):
    """A workspace, by its tenant's id and its own: the same ids in artifactr and reflexr."""

    tenant_id: str
    workspace_id: str


class DeadLetter(BaseModel):
    """An artifactr envelope the follower could not bridge, and why."""

    model_config = ConfigDict(frozen=True)

    seq: int
    """The envelope's position in the artifactr workspace's log."""

    envelope_id: str
    event_type: str
    """The artifactr event's type, such as `message_posted`."""

    error: str
    """What went wrong: the exception's type and message."""


type CauseKind = Literal["proposal", "artifact", "edit", "message", "turn"]
"""What a cause is recorded by: a proposal's, a created artifact's or a message's id; an edited
artifact's id and the version the edit makes, as `<id>@<version>`; or the id of an agent turn a
message started."""


class Cause(BaseModel):
    """The reflexr run behind an artifactr write: what continues its causal chain."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str
    """The run's chain: the id of its first event."""

    firing_id: str
    run_id: str
    depth: int
    """The depth of the run's own events: one deeper than what made its rule fire."""


type TrackedKind = Literal["item", "comment"]
"""What a tracker key names: an item a run files, or a comment it posts."""


class TrackedKey(NamedTuple):
    """A tracker key, by what it names."""

    kind: TrackedKind
    key: str


class Tracked(BaseModel):
    """A key a run writes to its workspace's tracker by, and what the write made."""

    model_config = ConfigDict(frozen=True)

    correlation_id: str
    """The chain of the run that claimed the key first."""

    ref: dict[str, JsonValue] | None = None
    """The item or comment the key made, as the tracker port names it; None while it is only
    claimed."""

    deleted: bool = False
    """Whether the item was found deleted: its key files nothing again."""

    written: dict[str, JsonValue] = {}
    """The value relayr last set on each of the item's fields, recorded before the write."""


class TrackerFollowing(BaseModel):
    """How far a workspace's tracker follower has read its bound project."""

    model_config = ConfigDict(frozen=True)

    project: str
    """The tracker project it reads: another one starts over."""

    cursor: tuple[datetime, str] | None = None
    """The `updated_at` and id of the last item it read, or None if the project had none."""

    swept_at: datetime
    """When it last read the whole project, by the follower's clock."""

    read_at: datetime | None = None
    """When it last read the project at all, by the follower's clock; None if no read said."""


class Snapshot(BaseModel):
    """An item of a bound project as the tracker follower last read it."""

    model_config = ConfigDict(frozen=True)

    item_id: str
    """The tracker's id for the item."""

    item: dict[str, JsonValue]
    """The item, as the tracker port reads it."""

    comments_after: datetime | None = None
    """The comments created before this were read; None if none were."""


class TrackerDeadLetter(BaseModel):
    """A change in a tracker the follower could not publish, and why."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    """The id the change's event was derived to have."""

    event_type: str
    """The event's type, such as `tracker:item_changed`."""

    item_id: str
    """The tracker's id for the item that changed."""

    error: str
    """What went wrong: the exception's type and message."""


class Ledger(Protocol):
    """Where followers keep their cursors, leases and dead letters, and runs their tracker keys."""

    async def acquire_lease(self, workspace: WorkspaceKey, holder: str, ttl: timedelta) -> bool:
        """Take or renew the workspace's lease for `ttl`. Return False if another holder has it."""
        ...

    async def release_lease(self, workspace: WorkspaceKey, holder: str) -> None:
        """Release the workspace's lease, if `holder` has it."""
        ...

    async def cursor(self, workspace: WorkspaceKey) -> int:
        """Return the `seq` of the last envelope the workspace's follower is done with, or 0."""
        ...

    async def save_cursor(self, workspace: WorkspaceKey, seq: int) -> None:
        """Save that the follower is done with `seq`. A cursor only moves forward."""
        ...

    async def dead_letter(self, workspace: WorkspaceKey, letter: DeadLetter) -> None:
        """Record an envelope the follower could not bridge; once per `seq`, the first kept."""
        ...

    async def dead_letters(self, workspace: WorkspaceKey) -> list[DeadLetter]:
        """Return the workspace's dead letters, in `seq` order."""
        ...

    async def record_cause(
        self, workspace: WorkspaceKey, kind: CauseKind, key: str, cause: Cause
    ) -> None:
        """Record the run behind a write, by what the follower will find it by; the first kept."""
        ...

    async def cause(self, workspace: WorkspaceKey, kind: CauseKind, key: str) -> Cause | None:
        """Return the run behind a write, or None if no run of a rule made it."""
        ...

    async def forget_causes(self, workspace: WorkspaceKey, *, older_than: timedelta) -> None:
        """Forget the causes recorded longer ago than `older_than`, by the ledger's clock."""
        ...

    async def followed(self) -> list[WorkspaceKey]:
        """Return every workspace a follower has held a lease on or saved a cursor for, in order.

        These are the workspaces to follow again when the application starts.
        """
        ...

    async def claim_tracked(
        self,
        workspace: WorkspaceKey,
        kind: TrackedKind,
        key: str,
        correlation_id: str,
        *,
        stale_after: timedelta,
    ) -> bool:
        """Claim a key before writing by it: True if the claim is the caller's.

        A new key is claimed with `correlation_id`. A key claimed longer ago than `stale_after`
        that has no record is claimed again, keeping its first correlation id. A key with a
        record, or claimed more recently, is not the caller's.
        """
        ...

    async def tracked(self, workspace: WorkspaceKey, kind: TrackedKind, key: str) -> Tracked | None:
        """Return a key's claim and record, or None if it was never claimed."""
        ...

    async def record_tracked(
        self, workspace: WorkspaceKey, kind: TrackedKind, key: str, ref: dict[str, JsonValue]
    ) -> dict[str, JsonValue] | None:
        """Record what a claimed key made, the first kept, and return the record kept.

        Returns None, recording nothing, if the key was never claimed.
        """
        ...

    async def every_tracked(self, workspace: WorkspaceKey) -> dict[TrackedKey, Tracked]:
        """Return every key claimed in the workspace, and what each made, by kind, then key."""
        ...

    async def release_tracked(self, workspace: WorkspaceKey, kind: TrackedKind, key: str) -> None:
        """Release a key's claim that recorded nothing, after a write that certainly didn't land."""
        ...

    async def mark_tracked_deleted(self, workspace: WorkspaceKey, key: str) -> None:
        """Mark an item's key deleted, so it files nothing again."""
        ...

    async def record_written(
        self, workspace: WorkspaceKey, key: str, fields: Mapping[str, JsonValue]
    ) -> None:
        """Record the values relayr is about to set on an item's fields, by its key."""
        ...

    async def forget_written(
        self, workspace: WorkspaceKey, key: str, fields: Collection[str]
    ) -> None:
        """Forget the values recorded for an item's fields."""
        ...

    async def consume_written(
        self, workspace: WorkspaceKey, key: str, values: Mapping[str, JsonValue]
    ) -> None:
        """Forget the values recorded for an item's fields that still hold the ones given.

        A field recorded since with another value keeps it.
        """
        ...

    async def record_tracker_write(
        self, workspace: WorkspaceKey, item_id: str, *, within: timedelta
    ) -> int:
        """Record a write relayr is about to make to an item, by the tracker's id for it.

        Returns how many it recorded within `within`, by the ledger's clock, this one included.
        """
        ...

    async def tracker_writes(self, workspace: WorkspaceKey, *, within: timedelta) -> dict[str, int]:
        """Return how many writes relayr recorded to each item within `within`, by its id.

        An item with none within it is left out.
        """
        ...

    async def acquire_tracker_lease(
        self, workspace: WorkspaceKey, holder: str, ttl: timedelta
    ) -> bool:
        """Take or renew the workspace's tracker lease for `ttl`; False if another holder has it.

        It is the tracker follower's, apart from the artifactr follower's lease.
        """
        ...

    async def release_tracker_lease(self, workspace: WorkspaceKey, holder: str) -> None:
        """Release the workspace's tracker lease, if `holder` has it."""
        ...

    async def tracker_following(self, workspace: WorkspaceKey) -> TrackerFollowing | None:
        """Return how far the workspace's tracker follower has read, or None if it never has."""
        ...

    async def save_tracker_following(
        self, workspace: WorkspaceKey, following: TrackerFollowing
    ) -> None:
        """Save how far the workspace's tracker follower has read.

        Within one project its cursor, its sweep and its last read only move forward; another
        project replaces them.
        """
        ...

    async def snapshots(
        self, workspace: WorkspaceKey, item_ids: Collection[str] | None = None
    ) -> dict[str, Snapshot]:
        """Return the snapshots of the items given, or of every item, by their ids."""
        ...

    async def save_snapshots(
        self, workspace: WorkspaceKey, snapshots: Collection[Snapshot]
    ) -> None:
        """Save items' snapshots, in place of those before."""
        ...

    async def forget_snapshots(
        self, workspace: WorkspaceKey, item_ids: Collection[str] | None = None
    ) -> None:
        """Forget the items given, or every item: their snapshots and relayr's writes to them."""
        ...

    async def tracker_dead_letter(self, workspace: WorkspaceKey, letter: TrackerDeadLetter) -> None:
        """Record a change the follower could not publish; once per event id, the first kept."""
        ...

    async def tracker_dead_letters(self, workspace: WorkspaceKey) -> list[TrackerDeadLetter]:
        """Return the workspace's tracker dead letters, by event id."""
        ...
