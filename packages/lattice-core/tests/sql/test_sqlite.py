"""SQLite engines: one connection, every transaction holding the write lock from its start."""

import asyncio
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.pool import NullPool

from lattice_core.sql.sqlite import create_sqlite_engine


async def test_transactions_take_turns_in_the_order_they_begin(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'core.db'}")
    try:
        async with engine.begin() as connection:
            await connection.execute(text("CREATE TABLE log (n INTEGER)"))

        async def append(n: int) -> None:
            async with engine.begin() as connection:
                count = await connection.scalar(text("SELECT count(*) FROM log"))
                await asyncio.sleep(0)  # another transaction would read the same count here
                await connection.execute(text("INSERT INTO log VALUES (:n)"), {"n": count})

        await asyncio.gather(*(append(n) for n in range(20)))
        async with engine.connect() as connection:
            logged = list(await connection.scalars(text("SELECT n FROM log ORDER BY rowid")))
        assert logged == list(range(20)), "no two transactions read the same count"
    finally:
        await engine.dispose()


async def test_an_engine_can_pool_connections_its_own_way(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'core.db'}", poolclass=NullPool)
    try:
        assert isinstance(engine.pool, NullPool)
        async with engine.begin() as connection:
            assert await connection.scalar(text("SELECT 1")) == 1
    finally:
        await engine.dispose()
