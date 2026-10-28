"""What a test's teardown cancels leaves no connection checked out (issue #836)."""

import asyncio
from pathlib import Path

import pytest

from artifactr.core import UserActor
from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import Workspaces
from tests.conftest import cancel_what_is_left, closing
from tests.databases import empty_database


@pytest.mark.parametrize("closes", range(1, 21))
async def test_a_close_cut_short_by_the_teardown_returns_its_connection(
    tmp_path: Path, closes: int
) -> None:
    """The teardown cancels what is left while SQLAlchemy is closing a read's session, the
    `closes`-th one; the database's disposal asserts that every connection came back."""
    async with empty_database("sqlite", tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        ws = await Workspaces(SqlStorage(engine)).open("acme", "prod", actor=UserActor(id="a"))
        seen: set[asyncio.Task[object]] = set()

        async def read() -> None:
            while True:
                await ws.threads()

        reading = asyncio.create_task(read())
        while True:
            running = {task for task in asyncio.all_tasks() if closing(task) and not task.done()}
            seen |= running
            if running and len(seen) >= closes:
                break
            await asyncio.sleep(0)
        await cancel_what_is_left()
        assert reading.cancelled()
