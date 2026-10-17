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

MIGRATION = (
    Path(__file__).parents[3] / "src/artifactr/files/sql/migrations/versions/0001_initial.py"
)


class Recorder:
    """Stands in for a connection to PostgreSQL: it records each statement it is asked."""

    dialect = postgresql.dialect()

    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, statement: object, parameters: object = None) -> None:
        self.statements.append(str(statement))


def _migration(recorder: Recorder, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    spec = importlib.util.spec_from_file_location("migration_initial", MIGRATION)
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
    _migration(migrated, monkeypatch).upgrade()
    created = Recorder()
    _on_postgresql(cast("Connection", created))
    assert sorted(created.statements) == sorted(migrated.statements)
    assert set(_migration(Recorder(), monkeypatch).TABLES) == set(metadata.tables)


def test_the_migration_keeps_every_table_to_its_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = Recorder()
    _migration(recorder, monkeypatch).upgrade()
    assert sum(s.startswith("CREATE POLICY") for s in recorder.statements) == len(metadata.tables)
    assert "SET STORAGE EXTERNAL" in recorder.statements[0]
