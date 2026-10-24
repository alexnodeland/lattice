"""People's answers to product analytics, in the application's database: portalr's first table.

``portalr_analytics_consent`` holds one row per person who has answered: their answer, when,
which deletion of their events is owed, by its number, until it is done, and how many they have
been owed. A deployment is its database, so an answer is per person and per deployment. It is
read on every event, from the application's database, so consent holds whether or not ClickHouse
is up. On PostgreSQL each transaction names its person, and row-level security keeps it to their
row, for the role the application connects as; without ``DATABASE_ADMIN_URL`` that role owns the
table, and row-level security doesn't hold it. Its Alembic migrations record their version in
``portalr_alembic_version``, apart from the application's own and the libraries'.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Final

from alembic import command
from alembic.config import Config
from sqlalchemy import (
    BigInteger,
    Boolean,
    Connection,
    DateTime,
    Integer,
    MetaData,
    String,
    and_,
    case,
    delete,
    literal,
    not_,
    select,
    text,
    update,
)
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


class _Answered:
    """A person's answer, and the deletion it owes: analytics' and replay's alike."""

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    given: Mapped[bool] = mapped_column(Boolean, nullable=False)
    answered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    delete_owed: Mapped[int] = mapped_column(Integer, nullable=False)
    """The deletion owed the person, by its number; 0 for none."""
    debts: Mapped[int] = mapped_column(Integer, nullable=False)
    """How many deletions the person has been owed: the next one's number is one more."""


class Answer(_Answered, Base):
    """A person's answer to product analytics."""

    __tablename__ = "portalr_analytics_consent"


class ReplayAnswer(_Answered, Base):
    """A person's answer to session replay, apart from analytics' (lattice RFC-0008, P8)."""

    __tablename__ = "portalr_replay_consent"


class Removal(Base):
    """A deletion owed a person removed from a tenant: their events there, up to the removal."""

    __tablename__ = "portalr_analytics_removals_owed"

    user_id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    removed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """When they were removed: their events from before it are deleted, and none after."""


class AuditCursor(Base):
    """How far a tenant's audit log in grantr has been read for removals."""

    __tablename__ = "portalr_analytics_audit_cursor"

    tenant_id: Mapped[str] = mapped_column(String, primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger().with_variant(Integer(), "sqlite"), nullable=False)
    """The `seq` of the last entry read: the log is read on from after it."""


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
            for table in ("portalr_analytics_consent", "portalr_replay_consent"):
                await connection.exec_driver_sql(
                    f'GRANT SELECT, INSERT, UPDATE ON {table} TO "{application_role}"'
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

    answers: type[_Answered] = Answer
    """The table of the answers it keeps: analytics', or replay's for :class:`SqlReplayConsent`."""

    def __init__(self, engine: AsyncEngine, *, owner: AsyncEngine | None = None) -> None:
        self._engine = engine
        self._owner = owner or engine

    async def given(self, user_id: str) -> bool:
        """Whether the person has said yes."""
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            answer = await connection.scalar(
                select(self.answers.given).where(self.answers.user_id == user_id)
            )
        return bool(answer)

    async def give(self, user_id: str, *, yes: bool) -> int | None:
        """Record the person's answer: the deletion now owed them, if any, by its number.

        One statement, which locks the row: a yes taken back takes the next number; a no again,
        or a yes, keeps the one owed, which a yes never cancels; and it touches nothing else.
        """
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            taken_back = and_(not_(literal(yes)), self.answers.given)
            owed = await connection.scalar(
                _upsert(connection)(self.answers)
                .values(
                    user_id=user_id,
                    given=yes,
                    answered_at=datetime.now(UTC),
                    delete_owed=0,
                    debts=0,
                )
                .on_conflict_do_update(
                    index_elements=[self.answers.user_id],
                    set_={
                        "given": yes,
                        "answered_at": datetime.now(UTC),
                        "delete_owed": case(
                            (taken_back, self.answers.debts + 1), else_=self.answers.delete_owed
                        ),
                        "debts": case(
                            (taken_back, self.answers.debts + 1), else_=self.answers.debts
                        ),
                    },
                )
                .returning(self.answers.delete_owed)
            )
        return owed or None

    async def owe(self, user_id: str) -> int:
        """Owe the person a new deletion, whatever their answer: its number.

        One statement, which locks the row and leaves the person's answer as it stands.
        """
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            owed = await connection.scalar(
                _upsert(connection)(self.answers)
                .values(
                    user_id=user_id,
                    given=False,
                    answered_at=datetime.now(UTC),
                    delete_owed=1,
                    debts=1,
                )
                .on_conflict_do_update(
                    index_elements=[self.answers.user_id],
                    set_={"delete_owed": self.answers.debts + 1, "debts": self.answers.debts + 1},
                )
                .returning(self.answers.delete_owed)
            )
        return int(owed or 0)

    async def owes(self, user_id: str) -> int | None:
        """The deletion owed the person, by its number, if any."""
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            owed = await connection.scalar(
                select(self.answers.delete_owed).where(self.answers.user_id == user_id)
            )
        return owed or None

    async def settled(self, user_id: str, debt: int) -> None:
        """Clear deletion `debt`, only if it is still the one owed."""
        async with self._engine.begin() as connection:
            await _as_person(connection, user_id)
            await connection.execute(
                update(self.answers)
                .where(self.answers.user_id == user_id, self.answers.delete_owed == debt)
                .values(delete_owed=0)
            )

    async def owing(self, most: int) -> list[tuple[str, int]]:
        """At most `most` people a deletion is owed, longest unanswered first, with its number.

        Read as the tables' owner. A person whose deletion keeps failing goes to the back as they
        are tried, since trying it doesn't change their row: the oldest answers come first.
        """
        async with self._owner.connect() as connection:
            rows = await connection.execute(
                select(self.answers.user_id, self.answers.delete_owed)
                .where(self.answers.delete_owed > 0)
                .order_by(self.answers.answered_at, self.answers.user_id)
                .limit(most)
            )
            return [(row.user_id, row.delete_owed) for row in rows]

    async def owe_removal(self, user_id: str, tenant: str, removed_at: datetime) -> None:
        """Owe the deletion of the person's events in the tenant, up to `removed_at` or later.

        Written as the tables' owner. A second removal before the first is settled owes up to
        the later one, whichever is read first.
        """
        owed = Removal.__table__.c.removed_at
        async with self._owner.begin() as connection:
            await connection.execute(
                _upsert(connection)(Removal)
                .values(user_id=user_id, tenant_id=tenant, removed_at=removed_at)
                .on_conflict_do_update(
                    index_elements=[Removal.user_id, Removal.tenant_id],
                    set_={"removed_at": case((owed < removed_at, removed_at), else_=owed)},
                )
            )

    async def removal_settled(self, user_id: str, tenant: str, removed_at: datetime) -> None:
        """Clear the deletion owed for that removal, only if no later one is owed since."""
        async with self._owner.begin() as connection:
            await connection.execute(
                delete(Removal).where(
                    Removal.user_id == user_id,
                    Removal.tenant_id == tenant,
                    Removal.removed_at == removed_at,
                )
            )

    async def removals_owed(
        self, most: int, *, before: datetime | None = None
    ) -> list[tuple[str, str, datetime]]:
        """At most `most` removals whose deletion is owed, the oldest first, removed `before`."""
        query = select(Removal.user_id, Removal.tenant_id, Removal.removed_at)
        if before is not None:
            query = query.where(Removal.removed_at < before)
        async with self._owner.connect() as connection:
            rows = await connection.execute(
                query.order_by(Removal.removed_at, Removal.user_id, Removal.tenant_id).limit(most)
            )
            return [(row.user_id, row.tenant_id, _utc(row.removed_at)) for row in rows]

    async def audit_cursor(self, tenant: str) -> int:
        """The `seq` up to which the tenant's audit log has been read for removals.

        Read as the tables' owner.
        """
        async with self._owner.connect() as connection:
            seq = await connection.scalar(
                select(AuditCursor.seq).where(AuditCursor.tenant_id == tenant)
            )
        return seq or 0

    async def advance_audit(self, tenant: str, seq: int) -> None:
        """Record that the tenant's audit log is read up to `seq`, if that is further."""
        read = AuditCursor.__table__.c.seq
        async with self._owner.begin() as connection:
            await connection.execute(
                _upsert(connection)(AuditCursor)
                .values(tenant_id=tenant, seq=seq)
                .on_conflict_do_update(
                    index_elements=[AuditCursor.tenant_id],
                    set_={"seq": case((read < seq, seq), else_=read)},
                )
            )


class SqlReplayConsent(SqlConsent):
    """People's answers to session replay, in the application's database, as analytics' are."""

    answers = ReplayAnswer


def _upsert(connection: AsyncConnection) -> Callable[..., Any]:
    """The dialect's INSERT, which has ON CONFLICT."""
    return postgres_insert if connection.dialect.name == "postgresql" else sqlite_insert


async def _as_person(connection: AsyncConnection, user_id: str) -> None:
    """Name the transaction's person to PostgreSQL, whose row-level security reads it."""
    if connection.dialect.name == "postgresql":
        await connection.execute(
            text("SELECT set_config('portalr.user_id', :person, true)"), {"person": user_id}
        )


def _utc(at: datetime) -> datetime:
    """A moment as the database gave it, in UTC: SQLite gives it without its zone."""
    return at if at.tzinfo is not None else at.replace(tzinfo=UTC)
