"""The ledger in a SQL database, through SQLAlchemy's asyncio extension.

It implements the whole [`Ledger`][relayr.ledger.Ledger] port with the same code on PostgreSQL
and SQLite. A workspace's lease and cursor are one row, locked while it changes.

Every database call is awaited to its end, even when its caller is cancelled, and the
cancellation is raised after it. SQLAlchemy takes a statement cancelled part-way for a lost
connection, which on SQLite can keep the database's write lock, or the pool's one connection.
"""

from collections.abc import Collection, Mapping
from datetime import UTC, datetime, timedelta
from typing import Final

from pydantic import JsonValue
from sqlalchemy import ColumnElement, delete, or_, select, update
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from lattice_core.sql.sessions import awaited_to_the_end, lock_row
from lattice_core.sql.tenancy import TENANT_KEY, TenantSession
from relayr.ledger import (
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
from relayr.sql.tables import (
    CauseRow,
    DeadLetterRow,
    FollowerRow,
    SnapshotRow,
    TrackedRow,
    TrackerDeadLetterRow,
    TrackerFollowerRow,
)


def _follower(workspace: WorkspaceKey) -> ColumnElement[bool]:
    return (FollowerRow.tenant_id == workspace.tenant_id) & (
        FollowerRow.workspace_id == workspace.workspace_id
    )


def _tracked(workspace: WorkspaceKey, kind: TrackedKind, key: str) -> ColumnElement[bool]:
    return (
        (TrackedRow.tenant_id == workspace.tenant_id)
        & (TrackedRow.workspace_id == workspace.workspace_id)
        & (TrackedRow.kind == kind)
        & (TrackedRow.key == key)
    )


def _in(
    workspace: WorkspaceKey,
    model: type[SnapshotRow | TrackerDeadLetterRow | TrackerFollowerRow],
) -> ColumnElement[bool]:
    return (model.tenant_id == workspace.tenant_id) & (model.workspace_id == workspace.workspace_id)


CHUNK: Final = 500
"""How many items' ids one statement names at most, well within SQLite's limit on parameters."""


async def _locked(session: AsyncSession, workspace: WorkspaceKey) -> FollowerRow:
    """Lock a workspace's row, which starts with its cursor at 0."""
    return await lock_row(
        session, FollowerRow, workspace, FollowerRow(**workspace._asdict(), seq=0)
    )


ACROSS_TENANTS: Final = frozenset({"followed"})
"""The read that spans tenants, which starts the followers: the only one that uses the
`across_tenants` engine."""


class SqlLedger:
    """A ledger in a SQL database, through SQLAlchemy's asyncio extension.

    Create the tables with [`migrate`][relayr.sql.migrate] first. The same code runs on
    PostgreSQL (with its default `READ COMMITTED` isolation) and on SQLite, whose engines must
    come from [`create_sqlite_engine`][relayr.sql.create_sqlite_engine].

    With `row_level_security`, each transaction names its tenant to PostgreSQL, whose
    policies, which the migrations create, then show it only that tenant's rows
    (`relayr.sql.tenancy`). The one read that spans tenants,
    [`followed`][relayr.sql.SqlLedger.followed], which starts the followers, goes to
    `across_tenants` instead: an engine whose role the policies don't hold, such as the
    tables' owner.

    Args:
        engine: The database to use. The ledger does not dispose of it.
        clock: Returns the current time, which leases expire by. Defaults to the system clock.
        row_level_security: Whether each transaction names its tenant to PostgreSQL.
        across_tenants: The engine for the read across tenants; required with
            `row_level_security`, and `engine` without it.

    Raises:
        ValueError: If `row_level_security` is on without `across_tenants`.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        clock: Clock = utc_now,
        row_level_security: bool = False,
        across_tenants: AsyncEngine | None = None,
    ) -> None:
        if row_level_security and across_tenants is None:
            raise ValueError("row-level security needs an engine for the reads across tenants")
        self._sessions = async_sessionmaker(
            engine,
            expire_on_commit=False,
            sync_session_class=TenantSession if row_level_security else Session,
        )
        self._across = async_sessionmaker(across_tenants or engine, expire_on_commit=False)
        self._clock = clock
        self._insert = postgresql.insert if engine.dialect.name == "postgresql" else sqlite.insert

    def _session(self, tenant_id: str) -> AsyncSession:
        """A session in a tenant."""
        return self._sessions(info={TENANT_KEY: tenant_id})

    async def _insert_once(
        self, row: CauseRow | DeadLetterRow | TrackedRow | TrackerDeadLetterRow
    ) -> bool:
        """Insert a row, unless one with its key is there: the first is kept. True if inserted."""
        async with self._session(row.tenant_id) as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return False
            return True

    @awaited_to_the_end
    async def acquire_lease(self, workspace: WorkspaceKey, holder: str, ttl: timedelta) -> bool:
        """Take or renew the workspace's lease for `ttl`. Return False if another holder has it."""
        # Normalized to UTC, because SQLite compares timestamps as text.
        now = self._clock().astimezone(UTC)
        async with self._session(workspace.tenant_id) as session, session.begin():
            await _locked(session, workspace)
            taken = await session.scalar(
                update(FollowerRow)
                .where(
                    _follower(workspace),
                    or_(
                        FollowerRow.holder == holder,
                        FollowerRow.expires_at.is_(None),
                        FollowerRow.expires_at <= now,
                    ),
                )
                .values(holder=holder, expires_at=now + ttl)
                .returning(FollowerRow.holder)
                .execution_options(synchronize_session=False)
            )
            return taken is not None

    @awaited_to_the_end
    async def release_lease(self, workspace: WorkspaceKey, holder: str) -> None:
        """Release the workspace's lease, if `holder` has it."""
        async with self._session(workspace.tenant_id) as session, session.begin():
            await session.execute(
                update(FollowerRow)
                .where(_follower(workspace), FollowerRow.holder == holder)
                .values(holder=None, expires_at=None)
            )

    @awaited_to_the_end
    async def cursor(self, workspace: WorkspaceKey) -> int:
        """Return the `seq` of the last envelope the workspace's follower is done with, or 0."""
        async with self._session(workspace.tenant_id) as session:
            row = await session.get(FollowerRow, workspace)
        return 0 if row is None else row.seq

    @awaited_to_the_end
    async def save_cursor(self, workspace: WorkspaceKey, seq: int) -> None:
        """Save that the follower is done with `seq`. A cursor only moves forward.

        The workspace's row is locked while it is compared, so saves from several processes
        leave the furthest.
        """
        async with self._session(workspace.tenant_id) as session, session.begin():
            row = await _locked(session, workspace)
            row.seq = max(row.seq, seq)

    @awaited_to_the_end
    async def dead_letter(self, workspace: WorkspaceKey, letter: DeadLetter) -> None:
        """Record an envelope the follower could not bridge; once per `seq`, the first kept."""
        await self._insert_once(DeadLetterRow(**workspace._asdict(), **letter.model_dump()))

    @awaited_to_the_end
    async def dead_letters(self, workspace: WorkspaceKey) -> list[DeadLetter]:
        """Return the workspace's dead letters, in `seq` order."""
        query = (
            select(DeadLetterRow)
            .where(
                DeadLetterRow.tenant_id == workspace.tenant_id,
                DeadLetterRow.workspace_id == workspace.workspace_id,
            )
            .order_by(DeadLetterRow.seq)
        )
        async with self._session(workspace.tenant_id) as session:
            rows = await session.scalars(query)
            return [
                DeadLetter(
                    seq=row.seq,
                    envelope_id=row.envelope_id,
                    event_type=row.event_type,
                    error=row.error,
                )
                for row in rows
            ]

    @awaited_to_the_end
    async def record_cause(
        self, workspace: WorkspaceKey, kind: CauseKind, key: str, cause: Cause
    ) -> None:
        """Record the run behind a write, by what the follower will find it by; the first kept."""
        # Normalized to UTC, because SQLite compares timestamps as text.
        at = self._clock().astimezone(UTC)
        await self._insert_once(
            CauseRow(
                **workspace._asdict(), kind=kind, key=key, recorded_at=at, **cause.model_dump()
            )
        )

    @awaited_to_the_end
    async def cause(self, workspace: WorkspaceKey, kind: CauseKind, key: str) -> Cause | None:
        """Return the run behind a write, or None if no run of a rule made it."""
        async with self._session(workspace.tenant_id) as session:
            row = await session.get(CauseRow, (*workspace, kind, key))
        if row is None:
            return None
        return Cause(
            correlation_id=row.correlation_id,
            firing_id=row.firing_id,
            run_id=row.run_id,
            depth=row.depth,
        )

    @awaited_to_the_end
    async def forget_causes(self, workspace: WorkspaceKey, *, older_than: timedelta) -> None:
        """Forget the causes recorded longer ago than `older_than`, by the ledger's clock."""
        before = self._clock().astimezone(UTC) - older_than
        async with self._session(workspace.tenant_id) as session, session.begin():
            await session.execute(
                delete(CauseRow).where(
                    CauseRow.tenant_id == workspace.tenant_id,
                    CauseRow.workspace_id == workspace.workspace_id,
                    CauseRow.recorded_at < before,
                )
            )

    @awaited_to_the_end
    async def followed(self) -> list[WorkspaceKey]:
        """Return every workspace a follower has held a lease on or saved a cursor for, in order."""
        query = select(FollowerRow.tenant_id, FollowerRow.workspace_id).order_by(
            FollowerRow.tenant_id, FollowerRow.workspace_id
        )
        async with self._across() as session:
            rows = await session.execute(query)
            return [WorkspaceKey(*row) for row in rows]

    @awaited_to_the_end
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

        A new key is inserted, once; a stale claim is taken again by one update, which a
        concurrent claim can't also make.
        """
        # Normalized to UTC, because SQLite compares timestamps as text.
        now = self._clock().astimezone(UTC)
        row = TrackedRow(
            **workspace._asdict(),
            kind=kind,
            key=key,
            correlation_id=correlation_id,
            claimed_at=now,
            deleted=False,
            written={},
        )
        if await self._insert_once(row):
            return True
        async with self._session(workspace.tenant_id) as session, session.begin():
            taken = await session.scalar(
                update(TrackedRow)
                .where(
                    _tracked(workspace, kind, key),
                    TrackedRow.ref.is_(None),
                    TrackedRow.claimed_at <= now - stale_after,
                )
                .values(claimed_at=now)
                .returning(TrackedRow.key)
                .execution_options(synchronize_session=False)
            )
            return taken is not None

    @awaited_to_the_end
    async def tracked(self, workspace: WorkspaceKey, kind: TrackedKind, key: str) -> Tracked | None:
        """Return a key's claim and record, or None if it was never claimed."""
        async with self._session(workspace.tenant_id) as session:
            row = await session.get(TrackedRow, (*workspace, kind, key))
        if row is None:
            return None
        return Tracked(
            correlation_id=row.correlation_id,
            ref=row.ref,
            deleted=row.deleted,
            written=row.written,
        )

    @awaited_to_the_end
    async def record_tracked(
        self, workspace: WorkspaceKey, kind: TrackedKind, key: str, ref: dict[str, JsonValue]
    ) -> dict[str, JsonValue] | None:
        """Record what a claimed key made, the first kept, and return the record kept."""
        async with self._session(workspace.tenant_id) as session, session.begin():
            await session.execute(
                update(TrackedRow)
                .where(_tracked(workspace, kind, key), TrackedRow.ref.is_(None))
                .values(ref=ref)
            )
            return await session.scalar(
                select(TrackedRow.ref).where(_tracked(workspace, kind, key))
            )

    @awaited_to_the_end
    async def release_tracked(self, workspace: WorkspaceKey, kind: TrackedKind, key: str) -> None:
        """Release a key's claim that recorded nothing, after a write that certainly didn't land."""
        async with self._session(workspace.tenant_id) as session, session.begin():
            await session.execute(
                delete(TrackedRow).where(_tracked(workspace, kind, key), TrackedRow.ref.is_(None))
            )

    @awaited_to_the_end
    async def mark_tracked_deleted(self, workspace: WorkspaceKey, key: str) -> None:
        """Mark an item's key deleted, so it files nothing again."""
        async with self._session(workspace.tenant_id) as session, session.begin():
            await session.execute(
                update(TrackedRow).where(_tracked(workspace, "item", key)).values(deleted=True)
            )

    @awaited_to_the_end
    async def record_written(
        self, workspace: WorkspaceKey, key: str, fields: Mapping[str, JsonValue]
    ) -> None:
        """Record the values relayr is about to set on an item's fields, by its key.

        The item's row is locked while it changes, so concurrent writes keep each other's.
        """
        async with self._session(workspace.tenant_id) as session, session.begin():
            row = await session.get(TrackedRow, (*workspace, "item", key), with_for_update=True)
            if row is not None:
                row.written = row.written | dict(fields)

    @awaited_to_the_end
    async def forget_written(
        self, workspace: WorkspaceKey, key: str, fields: Collection[str]
    ) -> None:
        """Forget the values recorded for an item's fields."""
        async with self._session(workspace.tenant_id) as session, session.begin():
            row = await session.get(TrackedRow, (*workspace, "item", key), with_for_update=True)
            if row is not None:
                row.written = {f: v for f, v in row.written.items() if f not in fields}

    @awaited_to_the_end
    async def consume_written(
        self, workspace: WorkspaceKey, key: str, values: Mapping[str, JsonValue]
    ) -> None:
        """Forget the values recorded for an item's fields that still hold the ones given.

        The item's row is locked while it changes, so a value recorded meanwhile is kept.
        """
        async with self._session(workspace.tenant_id) as session, session.begin():
            row = await session.get(TrackedRow, (*workspace, "item", key), with_for_update=True)
            if row is not None:
                row.written = {
                    f: v for f, v in row.written.items() if f not in values or values[f] != v
                }

    @awaited_to_the_end
    async def record_tracker_write(
        self, workspace: WorkspaceKey, item_id: str, *, within: timedelta
    ) -> int:
        """Record a write relayr is about to make to an item; return how many are within.

        The item's row is locked while it changes, so concurrent writes are each counted.
        """
        now = self._clock().astimezone(UTC)
        async with self._session(workspace.tenant_id) as session, session.begin():
            row = await lock_row(
                session,
                SnapshotRow,
                (*workspace, item_id),
                SnapshotRow(**workspace._asdict(), item_id=item_id, writes=[]),
            )
            since = now - within
            row.writes = [
                *(at for at in row.writes if datetime.fromisoformat(at) > since),
                now.isoformat(),
            ]
            return len(row.writes)

    @awaited_to_the_end
    async def acquire_tracker_lease(
        self, workspace: WorkspaceKey, holder: str, ttl: timedelta
    ) -> bool:
        """Take or renew the workspace's tracker lease for `ttl`; False if another holder has it."""
        now = self._clock().astimezone(UTC)
        async with self._session(workspace.tenant_id) as session, session.begin():
            row = await _following(session, workspace)
            if row.holder != holder and row.expires_at is not None and row.expires_at > now:
                return False
            row.holder, row.expires_at = holder, now + ttl
            return True

    @awaited_to_the_end
    async def release_tracker_lease(self, workspace: WorkspaceKey, holder: str) -> None:
        """Release the workspace's tracker lease, if `holder` has it."""
        async with self._session(workspace.tenant_id) as session, session.begin():
            await session.execute(
                update(TrackerFollowerRow)
                .where(_in(workspace, TrackerFollowerRow), TrackerFollowerRow.holder == holder)
                .values(holder=None, expires_at=None)
            )

    @awaited_to_the_end
    async def tracker_following(self, workspace: WorkspaceKey) -> TrackerFollowing | None:
        """Return how far the workspace's tracker follower has read, or None if it never has."""
        async with self._session(workspace.tenant_id) as session:
            row = await session.get(TrackerFollowerRow, workspace)
        if row is None or row.project is None or row.swept_at is None:
            return None
        cursor = None
        if row.cursor_at is not None and row.cursor_id is not None:
            cursor = (row.cursor_at, row.cursor_id)
        return TrackerFollowing(project=row.project, cursor=cursor, swept_at=row.swept_at)

    @awaited_to_the_end
    async def save_tracker_following(
        self, workspace: WorkspaceKey, following: TrackerFollowing
    ) -> None:
        """Save how far the workspace's tracker follower has read; forward only, per project.

        The follower's row is locked while it is compared, so saves from several processes
        leave the furthest.
        """
        async with self._session(workspace.tenant_id) as session, session.begin():
            row = await _following(session, workspace)
            cursor = following.cursor
            if row.project == following.project:
                if row.cursor_at is not None and row.cursor_id is not None:
                    held = (row.cursor_at, row.cursor_id)
                    cursor = held if cursor is None else max(held, cursor)
                if row.swept_at is not None and row.swept_at > following.swept_at:
                    following = following.model_copy(update={"swept_at": row.swept_at})
            row.project, row.swept_at = following.project, following.swept_at
            row.cursor_at, row.cursor_id = (None, None) if cursor is None else cursor

    @awaited_to_the_end
    async def snapshots(
        self, workspace: WorkspaceKey, item_ids: Collection[str] | None = None
    ) -> dict[str, Snapshot]:
        """Return the snapshots of the items given, or of every item, by their ids."""
        found: list[SnapshotRow] = []
        query = select(SnapshotRow).where(
            _in(workspace, SnapshotRow), SnapshotRow.item.is_not(None)
        )
        async with self._session(workspace.tenant_id) as session:
            if item_ids is None:
                found.extend(await session.scalars(query))
            for chunk in _chunks(item_ids or ()):
                found.extend(await session.scalars(query.where(SnapshotRow.item_id.in_(chunk))))
        return {
            row.item_id: Snapshot(
                item_id=row.item_id, item=row.item or {}, comments_after=row.comments_after
            )
            for row in found
        }

    @awaited_to_the_end
    async def save_snapshots(
        self, workspace: WorkspaceKey, snapshots: Collection[Snapshot]
    ) -> None:
        """Save items' snapshots, in place of those before, in one transaction.

        Each is inserted, or updated in place where its row is there, so relayr's writes to the
        item, which the row keeps too, are left as they are.
        """
        rows: list[dict[str, object]] = [
            {**workspace._asdict(), **snapshot.model_dump(), "writes": []} for snapshot in snapshots
        ]
        async with self._session(workspace.tenant_id) as session, session.begin():
            for at in range(0, len(rows), CHUNK):
                insert = self._insert(SnapshotRow).values(rows[at : at + CHUNK])
                await session.execute(
                    insert.on_conflict_do_update(
                        index_elements=["tenant_id", "workspace_id", "item_id"],
                        set_={
                            "item": insert.excluded.item,
                            "comments_after": insert.excluded.comments_after,
                        },
                    )
                )

    @awaited_to_the_end
    async def forget_snapshots(
        self, workspace: WorkspaceKey, item_ids: Collection[str] | None = None
    ) -> None:
        """Forget the items given, or every item: their snapshots and relayr's writes to them."""
        statement = delete(SnapshotRow).where(_in(workspace, SnapshotRow))
        async with self._session(workspace.tenant_id) as session, session.begin():
            if item_ids is None:
                await session.execute(statement)
            for chunk in _chunks(item_ids or ()):
                await session.execute(statement.where(SnapshotRow.item_id.in_(chunk)))

    @awaited_to_the_end
    async def tracker_dead_letter(self, workspace: WorkspaceKey, letter: TrackerDeadLetter) -> None:
        """Record a change the follower could not publish; once per event id, the first kept."""
        await self._insert_once(TrackerDeadLetterRow(**workspace._asdict(), **letter.model_dump()))

    @awaited_to_the_end
    async def tracker_dead_letters(self, workspace: WorkspaceKey) -> list[TrackerDeadLetter]:
        """Return the workspace's tracker dead letters, by event id."""
        query = (
            select(TrackerDeadLetterRow)
            .where(_in(workspace, TrackerDeadLetterRow))
            .order_by(TrackerDeadLetterRow.event_id)
        )
        async with self._session(workspace.tenant_id) as session:
            rows = await session.scalars(query)
            return [
                TrackerDeadLetter(
                    event_id=row.event_id,
                    event_type=row.event_type,
                    item_id=row.item_id,
                    error=row.error,
                )
                for row in rows
            ]


async def _following(session: AsyncSession, workspace: WorkspaceKey) -> TrackerFollowerRow:
    """Lock a workspace's tracker follower's row, which starts with nothing read."""
    return await lock_row(
        session, TrackerFollowerRow, workspace, TrackerFollowerRow(**workspace._asdict())
    )


def _chunks(item_ids: Collection[str]) -> list[list[str]]:
    ids = list(item_ids)
    return [ids[at : at + CHUNK] for at in range(0, len(ids), CHUNK)]
