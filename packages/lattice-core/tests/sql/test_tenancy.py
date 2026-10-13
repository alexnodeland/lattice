"""Row-level security: a transaction names its tenant, and policies keep rows to it."""

from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlalchemy import Connection, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.orm import Session

from lattice_core.sql import TENANT, TenantSession, create_sqlite_engine, grant, tenant_policy
from lattice_core.sql.tenancy import _set_tenant


class Recorder:
    """Stands in for a connection to PostgreSQL: it records each statement it is asked."""

    dialect = postgresql.dialect()

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    @property
    def statements(self) -> list[str]:
        return [statement for statement, _ in self.calls]

    def execute(self, statement: object, parameters: object = None) -> None:
        self.calls.append((str(statement), parameters))

    def scalar(self, statement: object) -> str:
        self.calls.append((str(statement), None))
        return "app schema"

    def scalars(self, statement: object, parameters: object = None) -> Iterator[str]:
        self.calls.append((str(statement), parameters))
        return iter(["numbered_id_seq"])


def test_a_transaction_names_its_tenant_to_postgresql() -> None:
    recorder = Recorder()
    session = cast("Session", SimpleNamespace(info={TENANT: "acme"}))
    _set_tenant(session, cast("Any", None), cast("Connection", recorder))
    assert recorder.calls == [
        (
            "SELECT set_config(:setting, :tenant, true)",
            {"setting": "lattice.tenant_id", "tenant": "acme"},
        )
    ]


@pytest.mark.parametrize("info", [{}, {TENANT: ""}, {TENANT: 7}])
async def test_a_session_must_name_its_tenant(tmp_path: Path, info: dict[str, object]) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'core.db'}")
    try:
        sessions = async_sessionmaker(engine, sync_session_class=TenantSession, info=info)
        with pytest.raises(RuntimeError, match="must name its tenant"):
            async with sessions.begin() as session:
                await session.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


async def test_sqlite_has_nothing_to_set(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'core.db'}")
    try:
        sessions = async_sessionmaker(engine, sync_session_class=TenantSession, info={TENANT: "a"})
        async with sessions.begin() as session:
            assert await session.scalar(text("SELECT 1")) == 1
    finally:
        await engine.dispose()


def test_a_policy_keeps_a_tables_rows_to_their_tenant() -> None:
    assert tenant_policy("notes", "owner") == (
        "ALTER TABLE notes ENABLE ROW LEVEL SECURITY",
        "CREATE POLICY notes_tenant ON notes"
        " USING (owner = current_setting('lattice.tenant_id', true))"
        " WITH CHECK (owner = current_setting('lattice.tenant_id', true))",
    )


def test_a_role_is_granted_the_schema_the_tables_and_their_sequences() -> None:
    recorder = Recorder()
    grant(cast("Connection", recorder), "app role", ["runs", "events"])
    assert [s for s in recorder.statements if s.startswith("GRANT")] == [
        'GRANT USAGE ON SCHEMA "app schema" TO "app role"',
        'GRANT SELECT, INSERT, UPDATE, DELETE ON events TO "app role"',
        'GRANT SELECT, INSERT, UPDATE, DELETE ON runs TO "app role"',
        'GRANT USAGE ON SEQUENCE numbered_id_seq TO "app role"',
    ]


async def test_sqlite_has_no_roles_to_grant(tmp_path: Path) -> None:
    engine = create_sqlite_engine(f"sqlite+aiosqlite:///{tmp_path / 'core.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(grant, "app role", ["runs"])
    finally:
        await engine.dispose()
