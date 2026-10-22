"""Calls to one app take turns: in one process, and across processes on PostgreSQL (ADR-0085)."""

from pathlib import Path

import anyio
import pytest

from artifactr.connect import ProcessLock
from artifactr.sql import AdvisoryLock, create_sqlite_engine
from tests.databases import empty_database


async def _overlapped(
    first: ProcessLock | AdvisoryLock, second: ProcessLock | AdvisoryLock
) -> bool:
    """Whether two holders of one key, each through its own lock, held it at once."""
    holding = 0
    overlapped = False

    async def hold(lock: ProcessLock | AdvisoryLock) -> None:
        nonlocal holding, overlapped
        async with lock.held("freecad 127.0.0.1"):
            holding += 1
            overlapped |= holding > 1
            await anyio.sleep(0.2)
            holding -= 1

    async with anyio.create_task_group() as holders:
        holders.start_soon(hold, first)
        holders.start_soon(hold, second)
    return overlapped


async def test_one_process_lock_takes_turns_and_two_dont() -> None:
    shared = ProcessLock()
    assert not await _overlapped(shared, shared)
    assert await _overlapped(ProcessLock(), ProcessLock()), "two processes' locks don't meet"


@pytest.mark.postgres
async def test_postgres_takes_turns_across_its_connections(tmp_path: Path) -> None:
    async with empty_database("postgres", tmp_path) as database:
        # Two engines, as two runner processes have: each its own pool, one database.
        first, second = database.engine(), database.engine()
        assert not await _overlapped(AdvisoryLock(first), AdvisoryLock(second))
        taken = anyio.Event()

        async def second_holder() -> None:
            async with AdvisoryLock(second).held("blender"):
                taken.set()

        async with anyio.create_task_group() as holders:
            async with AdvisoryLock(first).held("blender"):
                holders.start_soon(second_holder)
                await anyio.sleep(0.3)
                assert not taken.is_set(), "the second waits for the first"
            with anyio.fail_after(5):
                await taken.wait()


async def test_a_database_without_advisory_locks_is_refused(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'locks.db'}")
    with pytest.raises(ValueError, match="sqlite has no advisory locks"):
        AdvisoryLock(engine)
    await engine.dispose()
