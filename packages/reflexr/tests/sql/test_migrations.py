"""The packaged migrations build exactly the schema the models describe."""

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import JSON, Connection, column, func, insert, inspect, select, table, text
from sqlalchemy.ext.asyncio import AsyncEngine

from reflexr.core import (
    Envelope,
    Event,
    RuleArchived,
    RuleInstalled,
    RuleReset,
    RunSkipped,
    SourceActor,
    Tick,
    UnknownEvent,
)
from reflexr.sql import SqlStorage, create_schema, migrate
from reflexr.sql.schema import _alembic_config
from reflexr.sql.tables import VERSION_TABLE, EventRow, metadata
from reflexr.workspace import WorkspaceRef
from tests.clock import START
from tests.databases import empty_database
from tests.event_types import Deploy, ServiceError


def _differences(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(connection, opts={"version_table": VERSION_TABLE})
    return compare_metadata(context, metadata)


def _tables(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names())


async def test_migrations_build_the_models_schema(engine: AsyncEngine) -> None:
    await migrate(engine)
    async with engine.connect() as connection:
        assert await connection.run_sync(_differences) == []
        assert await connection.run_sync(_tables) == {*metadata.tables, VERSION_TABLE}


async def test_migrating_an_up_to_date_database_changes_nothing(engine: AsyncEngine) -> None:
    await migrate(engine)
    await migrate(engine)
    async with engine.connect() as connection:
        assert await connection.run_sync(_differences) == []


async def test_migrations_downgrade_to_an_empty_database(engine: AsyncEngine) -> None:
    await migrate(engine)
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "base"))
        assert await connection.run_sync(_tables) == {VERSION_TABLE}


async def test_create_schema_builds_the_same_schema(engine: AsyncEngine) -> None:
    await create_schema(engine)
    async with engine.connect() as connection:
        assert await connection.run_sync(_tables) == set(metadata.tables)
        assert await connection.run_sync(_differences) == []


def _stored(seq: int, event: Event) -> dict[str, Any]:
    """An events row as reflexr 0002 wrote it: the envelope's JSON, with no type column."""
    envelope = Envelope(
        seq=seq,
        id=f"e{seq}",
        ts=START,
        workspace_id="prod",
        actor=SourceActor(name="monitor"),
        correlation_id=f"e{seq}",
        event=event,
    )
    return {
        "tenant_id": "acme",
        "workspace_id": "prod",
        "seq": seq,
        "event_id": envelope.id,
        "envelope": envelope.model_dump(mode="json"),
    }


async def test_upgrading_fills_the_event_type_column_from_the_stored_envelopes(
    engine: AsyncEngine,
) -> None:
    events = table(
        "reflexr_events",
        column("tenant_id"),
        column("workspace_id"),
        column("seq"),
        column("event_id"),
        column("envelope", JSON()),
    )
    stored = [
        _stored(1, ServiceError(service="auth")),
        _stored(2, Deploy(service="auth")),
        _stored(3, UnknownEvent(unknown_type="app:pager.sent")),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "0002"))
        await connection.execute(insert(events), stored)
    await migrate(engine)
    async with engine.connect() as connection:
        query = select(EventRow.seq, EventRow.event_type).order_by(EventRow.seq)
        assert (await connection.execute(query)).all() == [
            (1, "app:service.error"),
            (2, "app:deploy.finished"),
            (3, "app:pager.sent"),
        ]
    storage = SqlStorage(engine)
    [deploy] = await storage.read(WorkspaceRef("acme", "prod"), types={"app:deploy.finished"})
    assert deploy.seq == 2
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "0002"))
        assert await connection.scalar(select(func.count()).select_from(events)) == 3, (
            "the rows outlive the column"
        )


def _qualify_facts(connection: Connection, step: str) -> None:
    """Run migration 0005's ``upgrade`` or ``downgrade`` by itself, a row per batch."""
    script = ScriptDirectory.from_config(_alembic_config(connection)).get_revision("0005")
    assert script is not None
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(script.module, "_BATCH", 1)
        with Operations.context(MigrationContext.configure(connection)):
            getattr(script.module, step)()


async def test_upgrading_qualifies_reflexrs_own_event_types(engine: AsyncEngine) -> None:
    events = table(
        "reflexr_events",
        column("tenant_id"),
        column("workspace_id"),
        column("seq"),
        column("event_id"),
        column("event_type"),
        column("envelope", JSON()),
    )

    def stored_as_0004(seq: int, event: Event, name: str, workspace: str = "prod") -> Any:
        row = _stored(seq, event)
        row["envelope"]["event"]["type"] = name
        return {**row, "workspace_id": workspace, "event_type": name}

    tick = Tick(schedule="clock", at=START)
    stored = [
        stored_as_0004(1, tick, "tick"),
        stored_as_0004(2, ServiceError(service="auth"), "app:service.error"),
        stored_as_0004(3, RunSkipped(run_id="fir_1", rule="app:triage"), "run_skipped"),
        stored_as_0004(1, tick, "tick", workspace="dev"),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "0004"))
        await connection.execute(insert(events), stored)
        await connection.run_sync(_qualify_facts, "upgrade")
        await connection.run_sync(lambda c: command.stamp(_alembic_config(c), "0005"))
    await migrate(engine)  # the later migrations, which the storage's models need
    storage = SqlStorage(engine)
    envelopes = await storage.read(WorkspaceRef("acme", "prod"))
    assert [e.event_type for e in envelopes] == [
        "reflexr:tick",
        "app:service.error",
        "reflexr:run_skipped",
    ]
    assert envelopes[0].event == tick
    [skipped] = await storage.read(WorkspaceRef("acme", "prod"), types={"reflexr:run_skipped"})
    assert skipped.seq == 3
    query = select(events.c.workspace_id, events.c.event_type, events.c.envelope).order_by(
        events.c.workspace_id, events.c.seq
    )
    async with engine.begin() as connection:
        rows = (await connection.execute(query)).all()
        assert [(w, t, e["event"]["type"]) for w, t, e in rows] == [
            ("dev", "reflexr:tick", "reflexr:tick"),
            ("prod", "reflexr:tick", "reflexr:tick"),
            ("prod", "app:service.error", "app:service.error"),
            ("prod", "reflexr:run_skipped", "reflexr:run_skipped"),
        ]
        await connection.run_sync(_qualify_facts, "downgrade")
        rows = (await connection.execute(query)).all()
    assert [(w, t, e["event"]["type"]) for w, t, e in rows] == [
        ("dev", "tick", "tick"),
        ("prod", "tick", "tick"),
        ("prod", "app:service.error", "app:service.error"),
        ("prod", "run_skipped", "run_skipped"),
    ]


async def test_upgrading_fills_the_rule_column_from_each_rules_versions(
    engine: AsyncEngine,
) -> None:
    events = table(
        "reflexr_events",
        column("tenant_id"),
        column("workspace_id"),
        column("seq"),
        column("event_id"),
        column("event_type"),
        column("envelope", JSON()),
    )

    def stored_as_0007(seq: int, event: Event, workspace: str = "prod") -> Any:
        row = _stored(seq, event)
        return {**row, "workspace_id": workspace, "event_type": row["envelope"]["event"]["type"]}

    installed = RuleInstalled(rule="chat:deploys", version=1, spec={}, provenance={})
    stored = [
        stored_as_0007(1, installed),
        stored_as_0007(
            2, RuleReset(rule="chat:deploys", generation=1, reason="changed", from_seq=1)
        ),
        stored_as_0007(3, ServiceError(service="auth")),
        stored_as_0007(4, RuleArchived(rule="chat:deploys", version=2, cancelled=0)),
        stored_as_0007(1, installed, workspace="dev"),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "0007"))
        await connection.execute(insert(events), stored)
    await migrate(engine)
    async with engine.connect() as connection:
        query = select(EventRow.workspace_id, EventRow.seq, EventRow.rule).order_by(
            EventRow.workspace_id, EventRow.seq
        )
        assert (await connection.execute(query)).all() == [
            ("dev", 1, "chat:deploys"),
            ("prod", 1, "chat:deploys"),
            ("prod", 2, None),
            ("prod", 3, None),
            ("prod", 4, "chat:deploys"),
        ], "only a rule's versions name it: not its resets"
    history = await SqlStorage(engine).rule_history(WorkspaceRef("acme", "prod"), "chat:deploys")
    assert [e.seq for e in history] == [1, 4]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "0007"))
        assert await connection.scalar(select(func.count()).select_from(events)) == 5, (
            "the rows outlive the column"
        )


ROW_SECURITY = text(
    "SELECT relrowsecurity FROM pg_class"
    " WHERE relnamespace = current_schema()::regnamespace AND relkind = 'r'"
)
POLICIES = text(
    "SELECT policyname, cmd, qual, with_check FROM pg_policies"
    " WHERE schemaname = current_schema() ORDER BY policyname"
)


@pytest.fixture
async def postgres(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    async with empty_database("postgres", tmp_path) as database:
        yield database.engine()


async def _row_security(engine: AsyncEngine) -> list[bool]:
    async with engine.connect() as connection:
        return list(await connection.scalars(ROW_SECURITY))


async def _policies(engine: AsyncEngine) -> list[tuple[Any, ...]]:
    async with engine.connect() as connection:
        return [tuple(row) for row in await connection.execute(POLICIES)]


@pytest.mark.postgres
async def test_migrations_keep_tenants_apart_on_postgresql(postgres: AsyncEngine) -> None:
    await migrate(postgres)
    assert len(await _policies(postgres)) == len(metadata.tables)
    async with postgres.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "0006"))
    assert await _policies(postgres) == []
    assert not any(await _row_security(postgres)), "every table's row-level security is off"


@pytest.mark.postgres
async def test_create_schema_keeps_tenants_apart_as_the_migrations_do(
    postgres: AsyncEngine, tmp_path: Path
) -> None:
    await migrate(postgres)
    async with empty_database("postgres", tmp_path) as other:
        engine = other.engine()
        await create_schema(engine)
        assert await _policies(engine) == await _policies(postgres)
