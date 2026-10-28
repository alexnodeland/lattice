"""What a test's teardown cancels leaves no connection checked out (issue #836)."""

import asyncio
from pathlib import Path

import pytest

from artifactr.core import UserActor
from artifactr.sql import SqlStorage, create_schema
from artifactr.workspace import Workspaces
from tests.conftest import cancel_what_is_left
from tests.databases import empty_database


@pytest.mark.parametrize("busy_for", [0.001 * n for n in range(1, 21)])
async def test_reads_cut_short_by_the_teardown_return_their_connections(
    tmp_path: Path, busy_for: float
) -> None:
    """Cancelled at whatever point a read has reached, as `_no_task_left` cancels it; the
    database's disposal asserts that every connection came back to its pool."""
    async with empty_database("sqlite", tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        ws = await Workspaces(SqlStorage(engine)).open("acme", "prod", actor=UserActor(id="a"))

        async def read() -> None:
            while True:
                await ws.threads()

        reading = asyncio.create_task(read())
        await asyncio.sleep(busy_for)
        await cancel_what_is_left()
        assert reading.cancelled()
