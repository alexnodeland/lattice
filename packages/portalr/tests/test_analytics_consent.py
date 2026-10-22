"""People's answers: no until they say yes, in memory and in the application's database."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import cast

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from portalr.analytics import Consent, InMemoryConsent
from portalr.analytics.sql import SqlConsent, migrate


async def answers(consent: Consent) -> None:
    assert not await consent.given("alice")
    await consent.give("alice", yes=True)
    assert await consent.given("alice")
    assert not await consent.given("bob")
    await consent.give("alice", yes=False)
    assert not await consent.given("alice")


async def test_answers_in_memory() -> None:
    await answers(InMemoryConsent())


async def test_answers_in_the_applications_database(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    await migrate(engine)
    await migrate(engine)  # again, as on every start: nothing changes
    await answers(SqlConsent(engine))
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
        version = await connection.scalar(text("SELECT version_num FROM portalr_alembic_version"))
    assert {"portalr_analytics_consent", "portalr_alembic_version"} <= set(tables)
    assert version == "0001"
    await engine.dispose()


async def test_an_application_role_is_granted_answers_on_postgresql_only(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    await migrate(engine, application_role="app")  # SQLite has no roles: nothing to grant
    await answers(SqlConsent(engine))
    await engine.dispose()


@pytest.mark.parametrize("given", [True, False])
async def test_an_answer_replaces_the_one_before(tmp_path: Path, given: bool) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    await migrate(engine)
    consent = SqlConsent(engine)
    await consent.give("alice", yes=not given)
    await consent.give("alice", yes=given)
    assert await consent.given("alice") is given
    await engine.dispose()


async def test_on_postgresql_the_application_role_may_read_and_write_answers_alone() -> None:
    statements: list[str] = []

    class Dialect:
        name = "postgresql"

    class Connection:
        dialect = Dialect()

        async def run_sync(self, _: object) -> None:
            return None

        async def exec_driver_sql(self, statement: str) -> None:
            statements.append(statement)

    class Engine:
        @asynccontextmanager
        async def begin(self) -> AsyncIterator[Connection]:
            yield Connection()

    await migrate(cast(AsyncEngine, Engine()), application_role="app")
    assert statements == ['GRANT SELECT, INSERT, UPDATE ON portalr_analytics_consent TO "app"']
