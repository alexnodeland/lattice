"""The ledger port: relayr's own storage, beside the libraries'.

For each followed workspace it keeps a cursor, the lease that lets one follower at a time follow
it, and the envelopes the follower could not bridge. For the outbound adapter it keeps what
caused each of its writes in artifactr: the reflexr run, so the follower continues its chain.
For the tracker connector it keeps each key a run writes to the tracker by: the claim made before
the write, the item or comment it made, and the values relayr last set on an item.
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
