"""What the SQL adapter adds to the contract: its locks, its engines, and awaiting every call."""

import asyncio
from datetime import timedelta

from sqlalchemy.ext.asyncio import AsyncEngine

from relayr.ledger import WorkspaceKey
from relayr.sql import SqlLedger, create_schema
from tests.clock import FakeClock

PROD = WorkspaceKey("acme", "prod")


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


async def test_one_of_two_concurrent_claims_wins(engine: AsyncEngine) -> None:
    await create_schema(engine)
    clock = FakeClock()
    ledger = SqlLedger(engine, clock=clock)
    stale = timedelta(seconds=30)

    async def claim(correlation_id: str) -> bool:
        return await ledger.claim_tracked(PROD, "item", "k", correlation_id, stale_after=stale)

    assert sorted(await asyncio.gather(claim("evt_1"), claim("evt_2"))) == [False, True]
    clock.advance(stale)
    assert sorted(await asyncio.gather(claim("evt_3"), claim("evt_4"))) == [False, True], (
        "and of two that take a stale claim again"
    )
