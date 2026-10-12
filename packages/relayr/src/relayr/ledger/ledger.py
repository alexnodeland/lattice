"""The ledger port: relayr's own storage, beside the libraries'.

For each followed workspace it keeps a cursor, the lease that lets one follower at a time follow
it, and the envelopes the follower could not bridge. Every adapter passes the one contract test,
`tests/ledger/test_contract.py`.
"""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import NamedTuple, Protocol

from pydantic import BaseModel, ConfigDict

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


class Ledger(Protocol):
    """Where followers keep their cursors, leases and dead letters."""

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

    async def followed(self) -> list[WorkspaceKey]:
        """Return every workspace a follower has held a lease on or saved a cursor for, in order.

        These are the workspaces to follow again when the application starts.
        """
        ...
