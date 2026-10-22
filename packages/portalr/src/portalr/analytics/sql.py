"""People's answers to product analytics, in the application's database: portalr's first table.

``portalr_analytics_consent`` holds one row per person who has answered: their answer, when, and
whether a deletion of their events is owed, until it is done. A deployment is its database, so
an answer is per person and per deployment. It is read on every event, from the application's
database, so consent holds whether or not ClickHouse is up. On PostgreSQL each transaction names
its person, and row-level security keeps it to their row, for the role the application connects
as; without ``DATABASE_ADMIN_URL`` that role owns the table, and row-level security doesn't hold
it. Its Alembic migrations record their version in ``portalr_alembic_version``, apart from the
application's own and the libraries'.
"""

from datetime import UTC, datetime
from typing import Final

from alembic import command
from alembic.config import Config
from sqlalchemy import Boolean, Connection, DateTime, MetaData, String, select, text, update
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

VERSION_TABLE: Final = "portalr_alembic_version"
"""Where Alembic records portalr's schema version."""

MIGRATION_LOCK: Final = 0x706F7274616C72
"""The PostgreSQL advisory lock two replicas starting at once take in turn to migrate."""


class Base(DeclarativeBase):
    """The declarative base of portalr's tables."""

    metadata = MetaData(naming_convention={"pk": "pk_%(table_name)s"})


class Answer(Base):
    """A person's answer to product analytics."""

    __tablename__ = "portalr_analytics_consent"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    given: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delete_pending: Mapped[bool] = mapped_column(Boolean, nullable=False)


metadata = Base.metadata


async def migrate(engine: AsyncEngine, *, application_role: str | None = None) -> None:
    """Upgrade the database to portalr's latest schema, as the tables' owner, on every start.

    Args:
        engine: The database, as the tables' owner.
        application_role: The role the application connects as, on PostgreSQL: granted reading
            and writing answers, and nothing more. It must exist.
    """
    async with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            # Held to the transaction's end: a second replica migrates after the first, and finds
            # nothing left to do.
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(:lock)"), {"lock": MIGRATION_LOCK}
            )
        await connection.run_sync(_upgrade)
        if application_role is not None and connection.dialect.name == "postgresql":
            await connection.exec_driver_sql(
                f'GRANT SELECT, INSERT, UPDATE ON portalr_analytics_consent TO "{application_role}"'
            )


def _upgrade(connection: Connection) -> None:
    config = Config()
    config.set_main_option("script_location", "portalr.analytics:migrations")
    config.attributes["connection"] = connection
    command.upgrade(config, "head")


class SqlConsent:
    """People's answers in the application's database.

    Args:
        engine: The database, as the role the application connects as: each transaction names
            its person, and on PostgreSQL row-level security keeps it to their row.
        owner: The database as the tables' owner, which reads every person's row: for the
            deletions owed, which a replica settles as it starts. ``engine`` without one.
    """

    def __init__(self, engine: AsyncEngine, *, owner: AsyncEngine | None = None) -> None:
        self._engine = engine
        self._owner = owner or engine

    async def given(self, user_id: str) -> bool:
        """Whether the person has said yes."""
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            answer = await connection.scalar(select(Answer.given).where(Answer.user_id == user_id))
        return bool(answer)

    async def give(self, user_id: str, *, yes: bool) -> bool:
        """Record the person's answer: whether a deletion of their events is now owed."""
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            before = (
                await connection.execute(
                    select(Answer.given, Answer.delete_pending).where(Answer.user_id == user_id)
                )
            ).first()
            owed = not yes and (
                before is not None and (bool(before.given) or bool(before.delete_pending))
            )
            row = {
                "user_id": user_id,
                "given": yes,
                "answered_at": datetime.now(UTC),
                "delete_pending": owed,
            }
            insert = (
                postgres_insert if connection.dialect.name == "postgresql" else sqlite_insert
            )(Answer).values(row)
            await connection.execute(
                insert.on_conflict_do_update(
                    index_elements=[Answer.user_id],
                    set_={k: v for k, v in row.items() if k != "user_id"},
                )
            )
        return owed

    async def owes(self, user_id: str) -> bool:
        """Whether a deletion of the person's events is owed."""
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            owed = await connection.scalar(
                select(Answer.delete_pending).where(Answer.user_id == user_id)
            )
        return bool(owed)

    async def settled(self, user_id: str) -> None:
        """Record that the deletion owed the person is done."""
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            await connection.execute(
                update(Answer).where(Answer.user_id == user_id).values(delete_pending=False)
            )

    async def owing(self) -> list[str]:
        """The people a deletion is owed, as the tables' owner reads them."""
        async with self._owner.connect() as connection:
            rows = await connection.scalars(
                select(Answer.user_id).where(Answer.delete_pending).order_by(Answer.user_id)
            )
            return list(rows)


async def _as_person(connection: AsyncConnection, user_id: str) -> None:
    """Name the transaction's person to PostgreSQL, whose row-level security reads it."""
    if connection.dialect.name == "postgresql":
        await connection.execute(
            text("SELECT set_config('portalr.user_id', :person, true)"), {"person": user_id}
        )
