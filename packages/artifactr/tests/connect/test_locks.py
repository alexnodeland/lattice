"""Calls to one app take turns: in one process, and across processes on PostgreSQL (ADR-0085)."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import anyio
import pytest
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.ext.asyncio import AsyncEngine

from artifactr.connect import ProcessLock
from artifactr.sql import AdvisoryLock, create_sqlite_engine
from tests.databases import empty_database

Lock = ProcessLock | AdvisoryLock


async def _overlapped(first: Lock, second: Lock) -> bool:
    """Whether two holders of one key, each through its own lock, held it at once."""
    holding = 0
    overlapped = False

    async def hold(lock: Lock) -> None:
        nonlocal holding, overlapped
        async with lock.held("freecad 127.0.0.1", wait=5):
            holding += 1
            overlapped |= holding > 1
            await anyio.sleep(0.2)
            holding -= 1

    async with anyio.create_task_group() as holders:
        holders.start_soon(hold, first)
        holders.start_soon(hold, second)
    return overlapped


async def _released(first: Lock, second: Lock) -> None:
    """The lock is let go of on an error and on a cancellation, and its wait is bounded."""
    with pytest.raises(RuntimeError):
        async with first.held("k", wait=5):
            raise RuntimeError("the call failed")
    async with second.held("k", wait=1):
        pass  # taken at once: the error let it go
    with anyio.move_on_after(0.2):
        async with first.held("k", wait=5):
            await anyio.sleep(5)  # cancelled while held
    async with second.held("k", wait=1):
        pass  # taken at once: the cancellation let it go
    holding, done = anyio.Event(), anyio.Event()

    async def hold() -> None:
        async with first.held("k", wait=5):
            holding.set()
            await done.wait()

    async with anyio.create_task_group() as holders:
        holders.start_soon(hold)
        await holding.wait()
        started = anyio.current_time()
        with pytest.raises(TimeoutError):
            async with second.held("k", wait=0.3):
                pass
        assert anyio.current_time() - started < 3, "the wait is bounded"
        done.set()


async def test_one_process_lock_takes_turns_and_two_dont() -> None:
    shared = ProcessLock()
    assert not await _overlapped(shared, shared)
    assert await _overlapped(ProcessLock(), ProcessLock()), "two processes' locks don't meet"
    await _released(shared, shared)


@pytest.mark.postgres
async def test_postgres_takes_turns_across_its_connections(tmp_path: Path) -> None:
    async with empty_database("postgres", tmp_path) as database:
        # Two engines, as two runner processes have: each its own pool, one database.
        first, second = database.engine(), database.engine()
        assert not await _overlapped(AdvisoryLock(first), AdvisoryLock(second))
        await _released(AdvisoryLock(first), AdvisoryLock(second))


async def test_a_database_without_advisory_locks_is_refused(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'locks.db'}")
    with pytest.raises(ValueError, match="sqlite has no advisory locks"):
        AdvisoryLock(engine)
    await engine.dispose()


class _Refused(Exception):
    def __init__(self, sqlstate: str) -> None:
        self.sqlstate = sqlstate


class _Connection:
    """What `AdvisoryLock` asks of a connection, without a PostgreSQL: each statement it is sent,
    and a lock refused as PostgreSQL refuses one, by its SQLSTATE."""

    def __init__(self, refused: str | None) -> None:
        self.refused = refused
        self.sent: list[str] = []
        self.invalidated = self.closed = False

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        yield

    async def execute(self, statement: object) -> None:
        self.sent.append(str(statement))
        if self.refused is not None and "pg_advisory_xact_lock" in str(statement):
            raise DBAPIError(str(statement), {}, _Refused(self.refused))

    async def invalidate(self) -> None:
        self.invalidated = True

    async def close(self) -> None:
        self.closed = True


class _Engine:
    """A PostgreSQL engine's face, whose pool is full when given no connection."""

    def __init__(self, connection: _Connection | None) -> None:
        self.dialect = SimpleNamespace(name="postgresql")
        self.connection = connection

    async def connect(self) -> _Connection:
        if self.connection is None:
            raise PoolTimeout("the pool is full")
        return self.connection


def _lock(connection: _Connection | None) -> AdvisoryLock:
    return AdvisoryLock(cast("AsyncEngine", _Engine(connection)))


async def test_a_full_pool_is_a_wait_past_its_bound() -> None:
    with pytest.raises(TimeoutError, match="no connection was free for the lock"):
        async with _lock(None).held("k", wait=1):
            pass


async def test_a_lock_not_taken_in_time_is_a_timeout_and_its_connection_thrown_away() -> None:
    connection = _Connection(refused="55P03")
    with pytest.raises(TimeoutError, match=r"wasn't taken within 0\.25s"):
        async with _lock(connection).held("k", wait=0.25):
            pass
    assert connection.sent[0] == "SET LOCAL lock_timeout = 250"
    assert (connection.invalidated, connection.closed) == (True, True)


async def test_another_refusal_is_the_databases_own() -> None:
    connection = _Connection(refused="57014")
    with pytest.raises(DBAPIError):
        async with _lock(connection).held("k", wait=1):
            pass
    assert (connection.invalidated, connection.closed) == (True, True)


async def test_a_lock_held_and_let_go_returns_its_connection() -> None:
    connection = _Connection(refused=None)
    async with _lock(connection).held("k", wait=1):
        assert any("pg_advisory_xact_lock" in sent for sent in connection.sent)
    assert (connection.invalidated, connection.closed) == (False, True)
