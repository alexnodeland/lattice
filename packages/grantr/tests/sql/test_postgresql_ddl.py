"""What grantr asks of PostgreSQL for row-level security, where no PostgreSQL is configured.

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

from grantr.sql.schema import _row_level_security

VERSIONS = Path(__file__).parents[2] / "src/grantr/sql/migrations/versions"
MIGRATION = VERSIONS / "0003_row_level_security.py"
CREATION = VERSIONS / "0005_tenant_creation_in_the_deployment_log.py"

POLICIES = 10
"""How many policies the migration creates: one per table it names, frozen in it."""


class Recorder:
    """Stands in for a connection to PostgreSQL: it records each statement it is asked."""

    def __init__(self, dialect: object | None = None) -> None:
        self.dialect = dialect or postgresql.dialect()
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
    op = SimpleNamespace(get_bind=lambda: recorder, execute=recorder.execute)
    monkeypatch.setattr(module, "op", op)
    return module


def test_create_schema_creates_the_policies_the_migration_does(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migrated = Recorder()
    _migration(migrated, monkeypatch).upgrade()
    _migration(migrated, monkeypatch, CREATION).upgrade()
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


def test_the_creation_migration_adds_and_drops_one_insert_only_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder()
    migration = _migration(recorder, monkeypatch, CREATION)
    migration.upgrade()
    [policy] = recorder.statements
    assert policy.startswith(
        "CREATE POLICY grantr_audit_tenant_creation ON grantr_audit FOR INSERT"
    )
    assert "tenant_id = '~deployment'" in policy
    assert "event_type = 'deployment_tenant_created'" in policy
    assert "= current_setting('lattice.tenant_id', true)" in policy, "of the transaction's tenant"
    recorder.calls.clear()
    migration.downgrade()
    assert recorder.statements == ["DROP POLICY grantr_audit_tenant_creation ON grantr_audit"]


def test_the_creation_migration_does_nothing_off_postgresql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = Recorder(SimpleNamespace(name="sqlite"))
    migration = _migration(recorder, monkeypatch, CREATION)
    migration.upgrade()
    migration.downgrade()
    assert recorder.calls == []
