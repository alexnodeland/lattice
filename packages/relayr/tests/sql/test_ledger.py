"""What the SQL adapter adds to the contract: its locks, its engines, and awaiting every call."""

import asyncio
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import NullPool

from relayr.ledger import WorkspaceKey
from relayr.sql import SqlLedger, create_schema, create_sqlite_engine
from relayr.sql.ledger import _to_the_end
from tests.clock import FakeClock

PROD = WorkspaceKey("acme", "prod")


@pytest.mark.parametrize("ending", ["returns", "raises", "is cancelled"])
async def test_a_cancelled_call_ends_before_the_cancellation_is_raised(ending: str) -> None:
    release = asyncio.Event()
    ended: list[str] = []

    async def call() -> None:
        await release.wait()
        ended.append(ending)
        if ending == "raises":
            raise RuntimeError("the statement failed")
        if ending == "is cancelled":
            raise asyncio.CancelledError

    caller = asyncio.create_task(_to_the_end(call()))
    for _ in range(3):  # cancelled again at every await, as anyio does
        await asyncio.sleep(0)
        caller.cancel()
    await asyncio.sleep(0)
    assert not caller.done(), "the call is still running"
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert ended == [ending]


async def test_an_engine_can_pool_connections_its_own_way(tmp_path: Path) -> None:
    engine = create_sqlite_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'relayr.db'}", poolclass=NullPool
    )
    try:
        assert isinstance(engine.pool, NullPool)
        await create_schema(engine)
        ledger = SqlLedger(engine)
        await ledger.save_cursor(PROD, 3)
        assert await ledger.cursor(PROD) == 3
    finally:
        await engine.dispose()


async def test_one_of_two_concurrent_first_leases_wins(engine: AsyncEngine) -> None:
    await create_schema(engine)
    ledger = SqlLedger(engine, clock=FakeClock())
    ttl = timedelta(seconds=30)
    taken = await asyncio.gather(*(ledger.acquire_lease(PROD, holder, ttl) for holder in "ab"))
    assert sorted(taken) == [False, True]


async def test_concurrent_saves_leave_the_furthest_cursor(engine: AsyncEngine) -> None:
    await create_schema(engine)
    ledger = SqlLedger(engine)
    await asyncio.gather(*(ledger.save_cursor(PROD, seq) for seq in (4, 9, 2)))
    assert await ledger.cursor(PROD) == 9
