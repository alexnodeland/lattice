"""What relayr asks of PostgreSQL for row-level security, where no PostgreSQL is configured.

The PostgreSQL tests run the same code against a database; these run it against a connection
that records what it is asked, so every run checks it.
"""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import cast

import pytest
from sqlalchemy import Connection
from sqlalchemy.dialects import postgresql

from relayr.sql.schema import _row_level_security

VERSIONS = Path(__file__).parents[2] / "src/relayr/sql/migrations/versions"
MIGRATION = VERSIONS / "0004_row_level_security.py"
TRACKER_ITEMS = VERSIONS / "0005_tracker_items.py"
TRACKER_FOLLOWERS = VERSIONS / "0006_tracker_followers.py"
"""The migrations that create policies: 0004 for the tables before it, and 0005 and 0006 for their
own."""

POLICIES = 3
"""How many policies the migration creates: one per table it names, frozen in it."""


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


def _migration(
    recorder: Recorder, monkeypatch: pytest.MonkeyPatch, path: Path = MIGRATION
) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    op = SimpleNamespace(
        get_bind=lambda: recorder,
        execute=recorder.execute,
        create_table=lambda *_, **__: None,
        drop_table=lambda *_, **__: None,
        f=str,
    )
    monkeypatch.setattr(module, "op", op)
    return module


def test_create_schema_creates_the_policies_the_migrations_do(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migrated = Recorder()
    _migration(migrated, monkeypatch).upgrade()
    _migration(migrated, monkeypatch, TRACKER_ITEMS).upgrade()
    _migration(migrated, monkeypatch, TRACKER_FOLLOWERS).upgrade()
    created = Recorder()
    _row_level_security(cast("Connection", created))
    assert sorted(created.statements) == sorted(migrated.statements)


def test_the_migration_creates_and_drops_the_policies(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    migration = _migration(recorder, monkeypatch)
    migration.upgrade()
    created = [s for s in recorder.statements if s.startswith("CREATE POLICY")]
    enabled = [s for s in recorder.statements if s.endswith("ENABLE ROW LEVEL SECURITY")]
    assert (len(created), len(enabled)) == (POLICIES, len(migration.TABLES))
    recorder.calls.clear()
    migration.downgrade()
    dropped = [s for s in recorder.statements if s.startswith("DROP POLICY")]
    disabled = [s for s in recorder.statements if s.endswith("DISABLE ROW LEVEL SECURITY")]
    assert (len(dropped), len(disabled)) == (POLICIES, len(migration.TABLES))


def test_the_tracker_items_migration_keeps_its_table_to_its_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder()
    _migration(recorder, monkeypatch, TRACKER_ITEMS).upgrade()
    assert recorder.statements == [
        "ALTER TABLE relayr_tracker_items ENABLE ROW LEVEL SECURITY",
        "CREATE POLICY relayr_tracker_items_tenant ON relayr_tracker_items"
        " USING (tenant_id = current_setting('lattice.tenant_id', true))"
        " WITH CHECK (tenant_id = current_setting('lattice.tenant_id', true))",
    ]


def test_the_tracker_followers_migration_keeps_its_tables_to_their_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder()
    _migration(recorder, monkeypatch, TRACKER_FOLLOWERS).upgrade()
    tables = ("relayr_tracker_followers", "relayr_tracker_snapshots", "relayr_tracker_dead_letters")
    assert recorder.statements == [
        statement
        for table in tables
        for statement in (
            f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
            f"CREATE POLICY {table}_tenant ON {table}"
            " USING (tenant_id = current_setting('lattice.tenant_id', true))"
            " WITH CHECK (tenant_id = current_setting('lattice.tenant_id', true))",
        )
    ]
