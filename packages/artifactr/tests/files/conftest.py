"""Shared fixtures: a clock, and the stores on memory, SQLite and, when configured, PostgreSQL.

On PostgreSQL the stores run as their tables' owner, and as a role their row-level security
policies hold.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from artifactr.files.blobs import Blobs, InMemoryBlobs, Quota
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
    async with stores_on(request.param, tmp_path, clock) as opened:
        yield opened


@asynccontextmanager
async def stores_on(
    backend: str,
    directory: Path,
    clock: FakeClock,
    *,
    workspace_quota: Quota | None = None,
    tenant_quota: Quota | None = None,
) -> AsyncIterator[Stores]:
    """The stores on a backend, the blob store held to the quotas given."""
    if backend == "memory":
        blobs = InMemoryBlobs(
            clock=clock, workspace_quota=workspace_quota, tenant_quota=tenant_quota
        )
        yield Stores(blobs, InMemoryCheckouts())
        return
    if backend == "postgres-rls":
        async with row_level_security(migrate) as (_, application):
            blobs = SqlBlobs(
                application,
                clock=clock,
                row_level_security=True,
                workspace_quota=workspace_quota,
                tenant_quota=tenant_quota,
            )
            yield Stores(blobs, SqlCheckouts(application, row_level_security=True))
        return
    async with empty_database(backend, directory) as database:
        engine = database.engine()
        await create_schema(engine)
        blobs = SqlBlobs(
            engine, clock=clock, workspace_quota=workspace_quota, tenant_quota=tenant_quota
        )
        yield Stores(blobs, SqlCheckouts(engine))


@dataclass
class Switch:
    """lattice-core's `Integrations`, with some keys off in some workspaces, recording each ask."""

    off: set[tuple[str, str, str]] = field(default_factory=set[tuple[str, str, str]])
    asked: list[tuple[str, str, str]] = field(default_factory=list[tuple[str, str, str]])

    async def is_enabled(self, tenant_id: str, workspace_id: str, key: str, /) -> bool:
        self.asked.append((tenant_id, workspace_id, key))
        return (tenant_id, workspace_id, key) not in self.off
