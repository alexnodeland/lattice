"""People's answers: no until they say yes, in memory and in the application's database."""

import importlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from portalr.analytics import Consent, InMemoryConsent
from portalr.analytics.sql import SqlConsent, migrate


async def answers(consent: Consent) -> None:
    assert not await consent.given("alice")
    assert await consent.give("alice", yes=False) is None, "a no never said yes owes nothing"
    assert await consent.give("alice", yes=True) is None
    assert await consent.given("alice")
    assert not await consent.given("bob")
    first = await consent.give("alice", yes=False)
    assert first is not None, "a yes taken back owes a deletion"
    assert not await consent.given("alice")
    assert await consent.owes("alice") == first
    assert await consent.give("alice", yes=False) == first, "a no again keeps the one owed"
    assert await consent.owing() == [("alice", first)]
    await consent.settled("alice", first)
    assert await consent.owes("alice") is None
    assert await consent.give("alice", yes=False) is None, "a no again owes nothing more"
    assert await consent.owing() == []
    await consent.give("bob", yes=True)
    await consent.give("bob", yes=False)
    assert await consent.give("bob", yes=True) is None, "a yes again owes nothing"
    assert await consent.owes("bob") is None


async def a_late_settling_clears_only_its_own_debt(consent: Consent) -> None:
    await consent.give("alice", yes=True)
    first = await consent.give("alice", yes=False)
    assert first is not None
    await consent.give("alice", yes=True)
    second = await consent.give("alice", yes=False)
    assert second is not None
    assert second != first
    await consent.settled("alice", first)
    assert await consent.owes("alice") == second, "the newer deletion is still owed"
    owed = await consent.owe("alice")
    assert owed not in (first, second)
    assert not await consent.given("alice"), "owing a deletion leaves the answer as it was"
    await consent.give("alice", yes=True)
    assert await consent.owe("alice") is not None
    assert await consent.given("alice"), "owing a deletion leaves a yes a yes"


async def test_answers_in_memory() -> None:
    await answers(InMemoryConsent())
    await a_late_settling_clears_only_its_own_debt(InMemoryConsent())


async def test_answers_in_the_applications_database(tmp_path: Path) -> None:
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'app.db'}")
    await migrate(engine)
    await migrate(engine)  # again, as on every start: nothing changes
    await answers(SqlConsent(engine))
    await a_late_settling_clears_only_its_own_debt(SqlConsent(engine))
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

        async def execute(self, statement: object, parameters: object = None) -> None:
            statements.append(str(statement))

        async def exec_driver_sql(self, statement: str) -> None:
            statements.append(statement)

    class Engine:
        @asynccontextmanager
        async def begin(self) -> AsyncIterator[Connection]:
            yield Connection()

    await migrate(cast(AsyncEngine, Engine()), application_role="app")
    assert statements == [
        "SELECT pg_advisory_xact_lock(:lock)",
        'GRANT SELECT, INSERT, UPDATE ON portalr_analytics_consent TO "app"',
    ]


MIGRATION = "portalr.analytics.migrations.versions.0001_analytics_consent"


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite"])
def test_the_migration_keeps_each_answer_to_its_person_on_postgresql_and_undoes_it(
    dialect: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    migration = importlib.import_module(MIGRATION)
    statements: list[str] = []

    class Op:
        def get_bind(self) -> object:
            return SimpleNamespace(dialect=SimpleNamespace(name=dialect))

        def execute(self, statement: str) -> None:
            statements.append(statement)

        def create_table(self, name: str, *_: object) -> None:
            statements.append(f"CREATE TABLE {name}")

        def drop_table(self, name: str) -> None:
            statements.append(f"DROP TABLE {name}")

        def f(self, name: str) -> str:
            return name

    monkeypatch.setattr(migration, "op", Op())
    migration.upgrade()
    migration.downgrade()
    policies = [s for s in statements if "POLICY" in s or "ROW LEVEL" in s]
    if dialect == "sqlite":
        assert policies == []
    else:
        assert policies == [
            "ALTER TABLE portalr_analytics_consent ENABLE ROW LEVEL SECURITY",
            "CREATE POLICY portalr_analytics_consent_person ON portalr_analytics_consent"
            " USING (user_id = current_setting('portalr.user_id', true))"
            " WITH CHECK (user_id = current_setting('portalr.user_id', true))",
            "DROP POLICY portalr_analytics_consent_person ON portalr_analytics_consent",
        ]
    assert statements[-1] == "DROP TABLE portalr_analytics_consent"


async def test_on_postgresql_each_transaction_names_its_person() -> None:
    said: list[tuple[str, object]] = []

    class Connection:
        dialect = SimpleNamespace(name="postgresql")

        async def execute(self, statement: object, parameters: object = None) -> None:
            said.append((str(statement), parameters))

        async def scalar(self, _: object) -> bool:
            return True

    class Engine:
        @asynccontextmanager
        async def begin(self) -> AsyncIterator[Connection]:
            yield Connection()

    consent = SqlConsent(cast(AsyncEngine, Engine()))
    assert await consent.given("alice")
    assert said[0] == (
        "SELECT set_config('portalr.user_id', :person, true)",
        {"person": "alice"},
    )
