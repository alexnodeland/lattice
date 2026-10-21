"""What the schema asks of PostgreSQL alone, where no PostgreSQL is configured.

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

from artifactr.files.sql.schema import _on_postgresql
from artifactr.files.sql.tables import metadata

MIGRATIONS = sorted(
    (Path(__file__).parents[3] / "src/artifactr/files/sql/migrations/versions").glob("0*.py")
)


class Recorder:
    """Stands in for a connection to PostgreSQL: it records each statement it is asked."""

    dialect = postgresql.dialect()

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: object, parameters: object = None) -> None:
        self.statements.append(str(statement))


def _migrations(recorder: Recorder, monkeypatch: pytest.MonkeyPatch) -> list[ModuleType]:
    """Every migration, in order, each asking the recorder."""
    return [_migration(path, recorder, monkeypatch) for path in MIGRATIONS]


def _migration(path: Path, recorder: Recorder, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    op = SimpleNamespace(
        get_bind=lambda: recorder,
        execute=recorder.execute,
        create_table=lambda *args, **kwargs: None,
        drop_table=recorder.execute,
        f=str,
    )
    monkeypatch.setattr(module, "op", op)
    return module


def test_create_schema_asks_what_the_migration_does(monkeypatch: pytest.MonkeyPatch) -> None:
    migrated = Recorder()
    migrations = _migrations(migrated, monkeypatch)
    for migration in migrations:
        migration.upgrade()
    created = Recorder()
    _on_postgresql(cast("Connection", created))
    assert sorted(created.statements) == sorted(migrated.statements)
    assert {table for m in migrations for table in m.TABLES} == set(metadata.tables)


def test_the_migration_keeps_every_table_to_its_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    for migration in _migrations(recorder, monkeypatch):
        migration.upgrade()
    assert sum(s.startswith("CREATE POLICY") for s in recorder.statements) == len(metadata.tables)
    assert "SET STORAGE EXTERNAL" in recorder.statements[0]
