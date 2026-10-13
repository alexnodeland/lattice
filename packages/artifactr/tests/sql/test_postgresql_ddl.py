"""What artifactr asks of PostgreSQL for row-level security, where no PostgreSQL is configured.

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

from artifactr.sql.schema import _row_level_security

MIGRATION = (
    Path(__file__).parents[2] / "src/artifactr/sql/migrations/versions/0006_row_level_security.py"
)

POLICIES = 11
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


def _migration(recorder: Recorder, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_rls", MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    op = SimpleNamespace(get_bind=lambda: recorder, execute=recorder.execute)
    monkeypatch.setattr(module, "op", op)
    return module


def test_create_schema_creates_the_policies_the_migration_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migrated = Recorder()
    _migration(migrated, monkeypatch).upgrade()
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
