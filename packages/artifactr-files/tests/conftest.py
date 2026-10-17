"""Shared fixtures: a clock, and the stores on memory, SQLite and, when configured, PostgreSQL.

On PostgreSQL the stores run as their tables' owner, and as a role their row-level security
policies hold.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from artifactr_files.blobs import Blobs, InMemoryBlobs
from artifactr_files.checkouts import Checkouts, InMemoryCheckouts
from artifactr_files.sql import SqlBlobs, SqlCheckouts, create_schema
from tests.clock import FakeClock
from tests.databases import (
    POSTGRES_URL,
    ROW_LEVEL_SECURITY,
    SQL_BACKENDS,
    empty_database,
    row_level_security,
)

BACKENDS = ["memory", *SQL_BACKENDS, ROW_LEVEL_SECURITY]


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Leave out the PostgreSQL tests unless a database is configured; the summary counts them."""
    if POSTGRES_URL:
        return
    postgres = [item for item in items if item.get_closest_marker("postgres")]
    config.hook.pytest_deselected(items=postgres)
    items[:] = [item for item in items if item not in postgres]


@dataclass(frozen=True)
class Stores:
    """The two stores, on one backend."""

    blobs: Blobs
    checkouts: Checkouts


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture(params=BACKENDS)
async def stores(
    request: pytest.FixtureRequest, tmp_path: Path, clock: FakeClock
) -> AsyncIterator[Stores]:
    if request.param == "memory":
        yield Stores(InMemoryBlobs(clock=clock), InMemoryCheckouts())
        return
    if request.param == "postgres-rls":
        async with row_level_security() as (_, application):
            yield Stores(
                SqlBlobs(application, clock=clock, row_level_security=True),
                SqlCheckouts(application, row_level_security=True),
            )
        return
    async with empty_database(request.param, tmp_path) as engine:
        await create_schema(engine)
        yield Stores(SqlBlobs(engine, clock=clock), SqlCheckouts(engine))
