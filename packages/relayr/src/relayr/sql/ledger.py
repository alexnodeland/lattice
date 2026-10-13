"""The ledger in a SQL database, through SQLAlchemy's asyncio extension.

It implements the whole [`Ledger`][relayr.ledger.Ledger] port with the same code on PostgreSQL
and SQLite. A workspace's lease and cursor are one row, locked while it changes.

Every database call is awaited to its end, even when its caller is cancelled, and the
cancellation is raised after it. SQLAlchemy takes a statement cancelled part-way for a lost
connection, which on SQLite can keep the database's write lock, or the pool's one connection.
"""

import contextlib
from datetime import UTC, timedelta
from typing import Final

from sqlalchemy import ColumnElement, delete, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from lattice_core.sql import awaited_to_the_end
from relayr.ledger import Cause, CauseKind, Clock, DeadLetter, WorkspaceKey, utc_now
from relayr.sql.tables import CauseRow, DeadLetterRow, FollowerRow
from relayr.sql.tenancy import TENANT, TenantSession


def _follower(workspace: WorkspaceKey) -> ColumnElement[bool]:
    return (FollowerRow.tenant_id == workspace.tenant_id) & (
        FollowerRow.workspace_id == workspace.workspace_id
    )


async def _locked(session: AsyncSession, workspace: WorkspaceKey) -> FollowerRow:
    """Lock a workspace's row (`SELECT ... FOR UPDATE`), inserting it first if it isn't there."""
    while (row := await session.get(FollowerRow, workspace, with_for_update=True)) is None:
        # A concurrent transaction may insert the row first. Then this insert fails, and the
        # next lookup waits for that transaction to end and locks its row instead.
        with contextlib.suppress(IntegrityError):
            async with session.begin_nested():
                session.add(FollowerRow(**workspace._asdict(), seq=0))
    return row


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

    def _session(self, tenant_id: str) -> AsyncSession:
        """A session in a tenant."""
        return self._sessions(info={TENANT: tenant_id})

    async def _insert_once(self, row: CauseRow | DeadLetterRow) -> None:
        """Insert a row, unless one with its key is there: the first is kept."""
        async with self._session(row.tenant_id) as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

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
