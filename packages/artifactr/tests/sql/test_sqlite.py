"""SQLite engines: one connection per engine, so a process's transactions take turns in order."""

import asyncio
from pathlib import Path

from sqlalchemy.pool import NullPool

from artifactr.core import UserActor
from artifactr.sql import SqlStorage, create_schema, create_sqlite_engine
from artifactr.workspace import Workspaces

ALICE = UserActor(id="alice")


async def test_transactions_in_one_process_take_turns_in_the_order_they_begin(
    tmp_path: Path,
) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'artifactr.db'}")
    try:
        await create_schema(engine)
        workspace = await Workspaces(SqlStorage(engine)).open("acme", "prod", actor=ALICE)
        titles = [f"thread {i}" for i in range(20)]
        await asyncio.gather(*(workspace.create_thread(title) for title in titles))
        assert [thread.title for thread in await workspace.threads()] == titles
    finally:
        await engine.dispose()


async def test_an_engine_can_pool_connections_its_own_way(tmp_path: Path) -> None:
    engine = create_sqlite_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'artifactr.db'}", poolclass=NullPool
    )
    try:
        assert isinstance(engine.pool, NullPool)
        await create_schema(engine)
        workspace = await Workspaces(SqlStorage(engine)).open("acme", "prod", actor=ALICE)
        await workspace.create_thread("Launch")
        assert await workspace.head_seq() == 1
    finally:
        await engine.dispose()
