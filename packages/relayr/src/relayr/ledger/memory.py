"""The ledger in memory: for tests, and for an application whose followers may start over."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from relayr.ledger.ledger import Clock, DeadLetter, WorkspaceKey, utc_now


@dataclass
class _Followed:
    seq: int = 0
    holder: str | None = None
    expires_at: datetime | None = None


class InMemoryLedger:
    """A ledger in this process's memory, lost when it ends.

    Args:
        clock: Returns the current time, which leases expire by. Defaults to the system clock.
    """

    def __init__(self, *, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._followed: dict[WorkspaceKey, _Followed] = {}
        self._dead_letters: dict[WorkspaceKey, dict[int, DeadLetter]] = {}

    async def acquire_lease(self, workspace: WorkspaceKey, holder: str, ttl: timedelta) -> bool:
        """Take or renew the workspace's lease for `ttl`. Return False if another holder has it."""
        now = self._clock()
        followed = self._followed.setdefault(workspace, _Followed())
        taken = followed.expires_at is not None and followed.expires_at > now
        if taken and followed.holder != holder:
            return False
        followed.holder, followed.expires_at = holder, now + ttl
        return True

    async def release_lease(self, workspace: WorkspaceKey, holder: str) -> None:
        """Release the workspace's lease, if `holder` has it."""
        followed = self._followed.get(workspace)
        if followed is not None and followed.holder == holder:
            followed.holder, followed.expires_at = None, None

    async def cursor(self, workspace: WorkspaceKey) -> int:
        """Return the `seq` of the last envelope the workspace's follower is done with, or 0."""
        followed = self._followed.get(workspace)
        return 0 if followed is None else followed.seq

    async def save_cursor(self, workspace: WorkspaceKey, seq: int) -> None:
        """Save that the follower is done with `seq`. A cursor only moves forward."""
        followed = self._followed.setdefault(workspace, _Followed())
        followed.seq = max(followed.seq, seq)

    async def dead_letter(self, workspace: WorkspaceKey, letter: DeadLetter) -> None:
        """Record an envelope the follower could not bridge; once per `seq`, the first kept."""
        self._dead_letters.setdefault(workspace, {}).setdefault(letter.seq, letter)

    async def dead_letters(self, workspace: WorkspaceKey) -> list[DeadLetter]:
        """Return the workspace's dead letters, in `seq` order."""
        letters = self._dead_letters.get(workspace, {})
        return [letters[seq] for seq in sorted(letters)]

    async def followed(self) -> list[WorkspaceKey]:
        """Return every workspace a follower has held a lease on or saved a cursor for, in order."""
        return sorted(self._followed)
