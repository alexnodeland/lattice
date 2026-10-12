"""The ledger in a SQL database, through SQLAlchemy's asyncio extension.

It implements the whole [`Ledger`][relayr.ledger.Ledger] port with the same code on PostgreSQL
and SQLite. A workspace's lease and cursor are one row, locked while it changes.

Every database call is awaited to its end, even when its caller is cancelled, and the
cancellation is raised after it. SQLAlchemy takes a statement cancelled part-way for a lost
connection, which on SQLite can keep the database's write lock, or the pool's one connection.
"""

import asyncio
import contextlib
import functools
from collections.abc import Awaitable, Callable
from datetime import UTC, timedelta
from types import CoroutineType
from typing import Any

from sqlalchemy import ColumnElement, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from relayr.ledger import Cause, CauseKind, Clock, DeadLetter, WorkspaceKey, utc_now
from relayr.sql.tables import CauseRow, DeadLetterRow, FollowerRow


# Shared verbatim with artifactr's src/artifactr/sql/storage.py, reflexr's
# src/reflexr/sql/storage.py and grantr's src/grantr/sql/storage.py; change all four.
async def _to_the_end[T](call: Awaitable[T]) -> T:
    """Await a database call to its end; a cancellation that came meanwhile is raised after."""
    task = asyncio.ensure_future(call)
    cancelled: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.wait([task])
        except asyncio.CancelledError as error:
            cancelled = error
    if cancelled is not None:
        if not task.cancelled():
            task.exception()
        raise cancelled
    return task.result()


# Shared verbatim with artifactr's src/artifactr/sql/storage.py, reflexr's
# src/reflexr/sql/storage.py and grantr's src/grantr/sql/storage.py; change all four.
def _awaited_to_the_end[**P, T](
    method: Callable[P, Awaitable[T]],
) -> Callable[P, "CoroutineType[Any, Any, T]"]:  # subscriptable at run time from Python 3.13
    """Await every call of a method to its end, with :func:`_to_the_end`."""

    @functools.wraps(method)
    async def call(*args: P.args, **kwargs: P.kwargs) -> T:
        return await _to_the_end(method(*args, **kwargs))

    return call


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


class SqlLedger:
    """A ledger in a SQL database, through SQLAlchemy's asyncio extension.

    Create the tables with [`migrate`][relayr.sql.migrate] first. The same code runs on
    PostgreSQL (with its default `READ COMMITTED` isolation) and on SQLite, whose engines must
    come from [`create_sqlite_engine`][relayr.sql.create_sqlite_engine].

    Args:
        engine: The database to use. The ledger does not dispose of it.
        clock: Returns the current time, which leases expire by. Defaults to the system clock.
    """

    def __init__(self, engine: AsyncEngine, *, clock: Clock = utc_now) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)
        self._clock = clock

    async def _insert_once(self, row: CauseRow | DeadLetterRow) -> None:
        """Insert a row, unless one with its key is there: the first is kept."""
        async with self._sessions() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

    @_awaited_to_the_end
    async def acquire_lease(self, workspace: WorkspaceKey, holder: str, ttl: timedelta) -> bool:
        """Take or renew the workspace's lease for `ttl`. Return False if another holder has it."""
        # Normalized to UTC, because SQLite compares timestamps as text.
        now = self._clock().astimezone(UTC)
        async with self._sessions() as session, session.begin():
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

    @_awaited_to_the_end
    async def release_lease(self, workspace: WorkspaceKey, holder: str) -> None:
        """Release the workspace's lease, if `holder` has it."""
        async with self._sessions() as session, session.begin():
            await session.execute(
                update(FollowerRow)
                .where(_follower(workspace), FollowerRow.holder == holder)
                .values(holder=None, expires_at=None)
            )

    @_awaited_to_the_end
    async def cursor(self, workspace: WorkspaceKey) -> int:
        """Return the `seq` of the last envelope the workspace's follower is done with, or 0."""
        async with self._sessions() as session:
            row = await session.get(FollowerRow, workspace)
        return 0 if row is None else row.seq

    @_awaited_to_the_end
    async def save_cursor(self, workspace: WorkspaceKey, seq: int) -> None:
        """Save that the follower is done with `seq`. A cursor only moves forward.

        The workspace's row is locked while it is compared, so saves from several processes
        leave the furthest.
        """
        async with self._sessions() as session, session.begin():
            row = await _locked(session, workspace)
            row.seq = max(row.seq, seq)

    @_awaited_to_the_end
    async def dead_letter(self, workspace: WorkspaceKey, letter: DeadLetter) -> None:
        """Record an envelope the follower could not bridge; once per `seq`, the first kept."""
        await self._insert_once(DeadLetterRow(**workspace._asdict(), **letter.model_dump()))

    @_awaited_to_the_end
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
        async with self._sessions() as session:
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

    @_awaited_to_the_end
    async def record_cause(
        self, workspace: WorkspaceKey, kind: CauseKind, key: str, cause: Cause
    ) -> None:
        """Record the run behind a write, by what the follower will find it by; the first kept."""
        await self._insert_once(
            CauseRow(**workspace._asdict(), kind=kind, key=key, **cause.model_dump())
        )

    @_awaited_to_the_end
    async def cause(self, workspace: WorkspaceKey, kind: CauseKind, key: str) -> Cause | None:
        """Return the run behind a write, or None if no run of a rule made it."""
        async with self._sessions() as session:
            row = await session.get(CauseRow, (*workspace, kind, key))
        if row is None:
            return None
        return Cause(
            correlation_id=row.correlation_id,
            firing_id=row.firing_id,
            run_id=row.run_id,
            depth=row.depth,
        )

    @_awaited_to_the_end
    async def followed(self) -> list[WorkspaceKey]:
        """Return every workspace a follower has held a lease on or saved a cursor for, in order."""
        query = select(FollowerRow.tenant_id, FollowerRow.workspace_id).order_by(
            FollowerRow.tenant_id, FollowerRow.workspace_id
        )
        async with self._sessions() as session:
            rows = await session.execute(query)
            return [WorkspaceKey(*row) for row in rows]
