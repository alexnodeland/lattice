"""Calls to one app take turns: in one process, and across processes on PostgreSQL (ADR-0085)."""

from pathlib import Path

import anyio
import pytest

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
