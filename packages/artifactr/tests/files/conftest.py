"""Shared fixtures: a clock, and the stores on memory, SQLite and, when configured, PostgreSQL.

On PostgreSQL the stores run as their tables' owner, and as a role their row-level security
policies hold.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import pytest

from artifactr.files.blobs import Blobs, InMemoryBlobs
from artifactr.files.checkouts import Checkouts, InMemoryCheckouts
from artifactr.files.sql import SqlBlobs, SqlCheckouts, create_schema, migrate
from tests.databases import (
    ROW_LEVEL_SECURITY,
    SQL_BACKENDS,
    empty_database,
    row_level_security,
)
from tests.files.clock import FakeClock

BACKENDS = ["memory", *SQL_BACKENDS, ROW_LEVEL_SECURITY]


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
        async with row_level_security(migrate) as (_, application):
            yield Stores(
                SqlBlobs(application, clock=clock, row_level_security=True),
                SqlCheckouts(application, row_level_security=True),
            )
        return
    async with empty_database(request.param, tmp_path) as database:
        engine = database.engine()
        await create_schema(engine)
        yield Stores(SqlBlobs(engine, clock=clock), SqlCheckouts(engine))
