"""Shared fixtures: a clock, and a ledger on memory, SQLite and, when configured, PostgreSQL.

On PostgreSQL the ledger runs as its tables' owner, and as a role their row-level security
policies hold.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from relayr.ledger import InMemoryLedger, Ledger
from relayr.sql import SqlLedger, create_schema
from tests.clock import FakeClock
from tests.databases import (
    POSTGRES_URL,
    ROW_LEVEL_SECURITY,
    SQL_BACKENDS,
    empty_database,
    row_level_security,
)
from tests.stack import Stack


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Leave out the PostgreSQL tests unless a database is configured; the summary counts them."""
    if POSTGRES_URL:
        return
    postgres = [item for item in items if item.get_closest_marker("postgres")]
    config.hook.pytest_deselected(items=postgres)
    items[:] = [item for item in items if item not in postgres]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(params=["memory", *SQL_BACKENDS, ROW_LEVEL_SECURITY])
async def ledger(
    request: pytest.FixtureRequest, tmp_path: Path, clock: FakeClock
) -> AsyncIterator[Ledger]:
    if request.param == "memory":
        yield InMemoryLedger(clock=clock)
        return
    if request.param == "postgres-rls":
        async with row_level_security() as (owner, application):
            yield SqlLedger(application, clock=clock, row_level_security=True, across_tenants=owner)
        return
    async with empty_database(request.param, tmp_path) as engine:
        await create_schema(engine)
        yield SqlLedger(engine, clock=clock)


@pytest.fixture
async def stack() -> AsyncIterator[Stack]:
    """The storage processes share; every process's followers stop when the test ends."""
    shared = Stack()
    yield shared
    for process in shared.processes:
        await process.followers.aclose()
