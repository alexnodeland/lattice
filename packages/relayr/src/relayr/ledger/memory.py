"""The ledger in memory: for tests, and for an application whose followers may start over."""

from collections.abc import Collection, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from pydantic import JsonValue

from relayr.ledger.ledger import (
    Cause,
    CauseKind,
    Clock,
    DeadLetter,
    Snapshot,
    Tracked,
    TrackedKind,
    TrackerDeadLetter,
    TrackerFollowing,
    WorkspaceKey,
    utc_now,
)


@dataclass
class _Followed:
    seq: int = 0
    holder: str | None = None
    expires_at: datetime | None = None


@dataclass
class _Lease:
    holder: str | None = None
    expires_at: datetime | None = None

    def take(self, holder: str, now: datetime, ttl: timedelta) -> bool:
        if self.expires_at is not None and self.expires_at > now and self.holder != holder:
            return False
        self.holder, self.expires_at = holder, now + ttl
        return True

    def release(self, holder: str) -> None:
        if self.holder == holder:
            self.holder, self.expires_at = None, None


@dataclass
class _Item:
    snapshot: Snapshot | None = None
    writes: list[datetime] = field(default_factory=list[datetime])


@dataclass
class _Tracked:
    correlation_id: str
    claimed_at: datetime
    ref: dict[str, JsonValue] | None = None
    deleted: bool = False
    written: dict[str, JsonValue] = field(default_factory=dict[str, JsonValue])


class InMemoryLedger:
    """A ledger in this process's memory, lost when it ends.

    Args:
        clock: Returns the current time, which leases expire by. Defaults to the system clock.
    """

    def __init__(self, *, clock: Clock = utc_now) -> None:
        self._clock = clock
        self._followed: dict[WorkspaceKey, _Followed] = {}
        self._dead_letters: dict[WorkspaceKey, dict[int, DeadLetter]] = {}
        self._causes: dict[tuple[WorkspaceKey, CauseKind, str], tuple[Cause, datetime]] = {}
        self._tracked: dict[tuple[WorkspaceKey, TrackedKind, str], _Tracked] = {}
        self._tracker_leases: dict[WorkspaceKey, _Lease] = {}
        self._following: dict[WorkspaceKey, TrackerFollowing] = {}
        self._items: dict[WorkspaceKey, dict[str, _Item]] = {}
        self._tracker_dead_letters: dict[WorkspaceKey, dict[str, TrackerDeadLetter]] = {}

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

    async def record_cause(
        self, workspace: WorkspaceKey, kind: CauseKind, key: str, cause: Cause
    ) -> None:
        """Record the run behind a write, by what the follower will find it by; the first kept."""
        self._causes.setdefault((workspace, kind, key), (cause, self._clock()))

    async def cause(self, workspace: WorkspaceKey, kind: CauseKind, key: str) -> Cause | None:
        """Return the run behind a write, or None if no run of a rule made it."""
        found = self._causes.get((workspace, kind, key))
        return None if found is None else found[0]

    async def forget_causes(self, workspace: WorkspaceKey, *, older_than: timedelta) -> None:
        """Forget the causes recorded longer ago than `older_than`, by the ledger's clock."""
        before = self._clock() - older_than
        self._causes = {
            key: (cause, at)
            for key, (cause, at) in self._causes.items()
            if key[0] != workspace or at >= before
        }

    async def followed(self) -> list[WorkspaceKey]:
        """Return every workspace a follower has held a lease on or saved a cursor for, in order."""
        return sorted(self._followed)

    async def claim_tracked(
        self,
        workspace: WorkspaceKey,
        kind: TrackedKind,
        key: str,
        correlation_id: str,
        *,
        stale_after: timedelta,
    ) -> bool:
        """Claim a key before writing by it: True if the claim is the caller's."""
        now = self._clock()
        found = self._tracked.get((workspace, kind, key))
        if found is None:
            self._tracked[workspace, kind, key] = _Tracked(correlation_id, now)
            return True
        if found.ref is not None or found.claimed_at > now - stale_after:
            return False
        found.claimed_at = now
        return True

    async def tracked(self, workspace: WorkspaceKey, kind: TrackedKind, key: str) -> Tracked | None:
        """Return a key's claim and record, or None if it was never claimed."""
        found = self._tracked.get((workspace, kind, key))
        if found is None:
            return None
        return Tracked(
            correlation_id=found.correlation_id,
            ref=found.ref,
            deleted=found.deleted,
            written=found.written,
        )

    async def record_tracked(
        self, workspace: WorkspaceKey, kind: TrackedKind, key: str, ref: dict[str, JsonValue]
    ) -> dict[str, JsonValue] | None:
        """Record what a claimed key made, the first kept, and return the record kept."""
        found = self._tracked.get((workspace, kind, key))
        if found is None:
            return None
        if found.ref is None:
            found.ref = ref
        return found.ref

    async def release_tracked(self, workspace: WorkspaceKey, kind: TrackedKind, key: str) -> None:
        """Release a key's claim that recorded nothing, after a write that certainly didn't land."""
        found = self._tracked.get((workspace, kind, key))
        if found is not None and found.ref is None:
            del self._tracked[workspace, kind, key]

    async def mark_tracked_deleted(self, workspace: WorkspaceKey, key: str) -> None:
        """Mark an item's key deleted, so it files nothing again."""
        found = self._tracked.get((workspace, "item", key))
        if found is not None:
            found.deleted = True

    async def record_written(
        self, workspace: WorkspaceKey, key: str, fields: Mapping[str, JsonValue]
    ) -> None:
        """Record the values relayr is about to set on an item's fields, by its key."""
        found = self._tracked.get((workspace, "item", key))
        if found is not None:
            found.written = found.written | dict(fields)

    async def forget_written(
        self, workspace: WorkspaceKey, key: str, fields: Collection[str]
    ) -> None:
        """Forget the values recorded for an item's fields."""
        found = self._tracked.get((workspace, "item", key))
        if found is not None:
            found.written = {f: v for f, v in found.written.items() if f not in fields}

    async def consume_written(
        self, workspace: WorkspaceKey, key: str, values: Mapping[str, JsonValue]
    ) -> None:
        """Forget the values recorded for an item's fields that still hold the ones given."""
        found = self._tracked.get((workspace, "item", key))
        if found is not None:
            found.written = {
                f: v for f, v in found.written.items() if f not in values or values[f] != v
            }

    async def record_tracker_write(
        self, workspace: WorkspaceKey, item_id: str, *, within: timedelta
    ) -> int:
        """Record a write relayr is about to make to an item; return how many are within."""
        now = self._clock()
        item = self._items.setdefault(workspace, {}).setdefault(item_id, _Item())
        item.writes = [at for at in item.writes if at > now - within] + [now]
        return len(item.writes)

    async def acquire_tracker_lease(
        self, workspace: WorkspaceKey, holder: str, ttl: timedelta
    ) -> bool:
        """Take or renew the workspace's tracker lease for `ttl`; False if another holder has it."""
        return self._tracker_leases.setdefault(workspace, _Lease()).take(holder, self._clock(), ttl)

    async def release_tracker_lease(self, workspace: WorkspaceKey, holder: str) -> None:
        """Release the workspace's tracker lease, if `holder` has it."""
        lease = self._tracker_leases.get(workspace)
        if lease is not None:
            lease.release(holder)

    async def tracker_following(self, workspace: WorkspaceKey) -> TrackerFollowing | None:
        """Return how far the workspace's tracker follower has read, or None if it never has."""
        return self._following.get(workspace)

    async def save_tracker_following(
        self, workspace: WorkspaceKey, following: TrackerFollowing
    ) -> None:
        """Save how far the workspace's tracker follower has read; forward only, per project."""
        before = self._following.get(workspace)
        self._following[workspace] = (
            following
            if before is None or before.project != following.project
            else _furthest(before, following)
        )

    async def snapshots(
        self, workspace: WorkspaceKey, item_ids: Collection[str] | None = None
    ) -> dict[str, Snapshot]:
        """Return the snapshots of the items given, or of every item, by their ids."""
        items = self._items.get(workspace, {})
        wanted = items.keys() if item_ids is None else set(item_ids) & items.keys()
        return {
            item_id: snapshot
            for item_id in wanted
            if (snapshot := items[item_id].snapshot) is not None
        }

    async def save_snapshots(
        self, workspace: WorkspaceKey, snapshots: Collection[Snapshot]
    ) -> None:
        """Save items' snapshots, in place of those before."""
        items = self._items.setdefault(workspace, {})
        for snapshot in snapshots:
            items.setdefault(snapshot.item_id, _Item()).snapshot = snapshot

    async def forget_snapshots(
        self, workspace: WorkspaceKey, item_ids: Collection[str] | None = None
    ) -> None:
        """Forget the items given, or every item: their snapshots and relayr's writes to them."""
        items = self._items.get(workspace, {})
        for item_id in list(items) if item_ids is None else item_ids:
            items.pop(item_id, None)

    async def tracker_dead_letter(self, workspace: WorkspaceKey, letter: TrackerDeadLetter) -> None:
        """Record a change the follower could not publish; once per event id, the first kept."""
        self._tracker_dead_letters.setdefault(workspace, {}).setdefault(letter.event_id, letter)

    async def tracker_dead_letters(self, workspace: WorkspaceKey) -> list[TrackerDeadLetter]:
        """Return the workspace's tracker dead letters, by event id."""
        letters = self._tracker_dead_letters.get(workspace, {})
        return [letters[event_id] for event_id in sorted(letters)]


def _furthest(before: TrackerFollowing, after: TrackerFollowing) -> TrackerFollowing:
    """The further of two readings of one project: each of cursor and sweep only moves forward."""
    cursors = [cursor for cursor in (before.cursor, after.cursor) if cursor is not None]
    return TrackerFollowing(
        project=after.project,
        cursor=max(cursors, default=None),
        swept_at=max(before.swept_at, after.swept_at),
    )
