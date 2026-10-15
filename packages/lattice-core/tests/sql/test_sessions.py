"""Awaiting a call to its end, and locking a row, inserted if it isn't there."""

import asyncio
from pathlib import Path
from typing import Any, override

import pytest
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from lattice_core.sql.sessions import awaited_to_the_end, lock_row, to_the_end
from lattice_core.sql.sqlite import create_sqlite_engine


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

    caller = asyncio.create_task(to_the_end(call()))
    for _ in range(3):  # cancelled again at every await, as anyio does
        await asyncio.sleep(0)
        caller.cancel()
    await asyncio.sleep(0)
    assert not caller.done(), "the call is still running"
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await caller
    assert ended == [ending]


async def test_a_call_not_cancelled_returns_its_result() -> None:
    class Store:
        @awaited_to_the_end
        async def read(self, key: str) -> str:
            await asyncio.sleep(0)
            return key.upper()

    assert await Store().read("row") == "ROW"
    assert Store.read.__name__ == "read", "the method keeps its name"


class Base(DeclarativeBase):
    pass


class Counter(Base):
    __tablename__ = "counters"

    name: Mapped[str] = mapped_column(primary_key=True)
    count: Mapped[int]


async def _sessions(tmp_path: Path) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'core.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def test_a_missing_row_is_inserted_and_an_existing_one_locked(tmp_path: Path) -> None:
    engine, sessions = await _sessions(tmp_path)
    try:
        async with sessions.begin() as session:
            row = await lock_row(session, Counter, ("a",), Counter(name="a", count=0))
            row.count += 1
        async with sessions.begin() as session:
            row = await lock_row(session, Counter, ("a",), Counter(name="a", count=0))
            assert row.count == 1, "the row there is locked, not replaced"
    finally:
        await engine.dispose()


class MissesOnce(AsyncSession):
    """A session whose first lookup misses the row, as if another transaction inserted it since."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.looked = 0

    @override
    async def get(self, *args: Any, **kwargs: Any) -> Any:
        self.looked += 1
        return None if self.looked == 1 else await super().get(*args, **kwargs)


async def test_a_row_another_transaction_inserted_first_is_locked(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'core.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(insert(Counter).values(name="a", count=7))
        sessions = async_sessionmaker(engine, class_=MissesOnce, expire_on_commit=False)
        async with sessions.begin() as session:
            row = await lock_row(session, Counter, ("a",), Counter(name="a", count=0))
            looked = session.looked
        assert (row.count, looked) == (7, 2), "the insert failed, then it was locked"
    finally:
        await engine.dispose()
