"""The packaged migrations build exactly the schema the models describe."""

from datetime import UTC, datetime
from typing import Any

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import JSON, Connection, column, func, insert, inspect, select, table
from sqlalchemy.ext.asyncio import AsyncEngine

from artifactr.core import (
    AppEvent,
    ArtifactCreated,
    Envelope,
    Event,
    ThreadCreated,
    UnknownEvent,
    UserActor,
)
from artifactr.sql import SqlStorage, create_schema, migrate
from artifactr.sql.schema import _alembic_config
from artifactr.sql.tables import VERSION_TABLE, EventRow, metadata
from artifactr.workspace import Scope


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


def _stored(seq: int, event: Event, thread_id: str | None = None) -> dict[str, Any]:
    """An events row as artifactr 0001 wrote it: the envelope's JSON, with no other columns."""
    envelope = Envelope(
        seq=seq,
        id=f"e{seq}",
        ts=datetime(2026, 9, 28, tzinfo=UTC),
        workspace_id="ws_1",
        thread_id=thread_id,
        actor=UserActor(id="alice"),
        event=event,
    )
    return {
        "tenant_id": "tenant_a",
        "workspace_id": "ws_1",
        "seq": seq,
        "envelope": envelope.model_dump(mode="json"),
    }


async def test_upgrading_fills_the_new_columns_from_the_stored_envelopes(
    engine: AsyncEngine,
) -> None:
    events = table(
        "artifactr_events",
        column("tenant_id"),
        column("workspace_id"),
        column("seq"),
        column("envelope", JSON()),
    )
    stored = [
        _stored(1, ThreadCreated(thread_id="t1", title="one"), "t1"),
        _stored(2, ArtifactCreated(artifact_id="n1", kind="note", version=1, data={}), "t2"),
        _stored(3, AppEvent(name="exported")),
        _stored(4, UnknownEvent.model_validate({"type": "thread_pinned"}), "t2"),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.upgrade(_alembic_config(c), "0001"))
        await connection.execute(insert(events), stored)
    await migrate(engine)
    async with engine.connect() as connection:
        query = select(EventRow.seq, EventRow.event_type, EventRow.thread_id).order_by(EventRow.seq)
        assert (await connection.execute(query)).all() == [
            (1, "thread_created", "t1"),
            (2, "artifact_created", "t2"),
            (3, "app_event", None),
            (4, "thread_pinned", "t2"),
        ]
    followers_of_t1 = await SqlStorage(engine).read(Scope("tenant_a", "ws_1"), threads={"t1"})
    assert [envelope.seq for envelope in followers_of_t1] == [1, 2, 3]
    async with engine.begin() as connection:
        await connection.run_sync(lambda c: command.downgrade(_alembic_config(c), "0001"))
        assert await connection.scalar(select(func.count()).select_from(events)) == 4, (
            "the rows outlive the columns"
        )
