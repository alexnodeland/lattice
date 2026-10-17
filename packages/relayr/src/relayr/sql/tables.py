"""relayr's tables, as SQLAlchemy declarative models.

Table names start with `relayr_`, so they share a database with the application's own tables and
the libraries'.
"""

from datetime import UTC, datetime
from typing import Any, Final, override

from sqlalchemy import JSON, BigInteger, DateTime, Dialect, Index, MetaData, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

VERSION_TABLE: Final = "relayr_alembic_version"
"""Where Alembic records relayr's schema version, apart from the application's own."""


class Base(DeclarativeBase):
    """The declarative base of relayr's tables."""

    metadata = MetaData(naming_convention={"pk": "pk_%(table_name)s"})


metadata = Base.metadata
"""The schema the migrations build, and that [`create_schema`][relayr.sql.create_schema] creates."""


class UtcDateTime(TypeDecorator[datetime]):
    """A point in time, stored and read back in UTC.

    SQLite keeps timestamps as text without their zone and compares them as text, so every value
    is converted to UTC before it is stored, and reads attach UTC.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    @override
    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.astimezone(UTC)

    @override
    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class FollowerRow(Base):
    """A followed workspace: its follower's cursor, and the lease one follower holds at a time."""

    __tablename__ = "relayr_followers"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger)
    """The `seq` of the last artifactr envelope the follower is done with."""

    holder: Mapped[str | None]
    """Who holds the lease, if anyone does."""

    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    """When the lease lapses unless it is renewed."""


class CauseRow(Base):
    """The reflexr run behind an artifactr write, by what the follower finds it by."""

    __tablename__ = "relayr_causes"
    __table_args__ = (
        Index("ix_relayr_causes_recorded", "tenant_id", "workspace_id", "recorded_at"),
    )

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(primary_key=True)
    """What the key is: a `proposal`, `artifact`, `edit`, `message` or `turn`."""

    key: Mapped[str] = mapped_column(primary_key=True)

    correlation_id: Mapped[str]
    firing_id: Mapped[str]
    run_id: Mapped[str]
    depth: Mapped[int]
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    """When it was recorded, which it is forgotten by."""


class DeadLetterRow(Base):
    """An artifactr envelope the follower could not bridge."""

    __tablename__ = "relayr_dead_letters"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    envelope_id: Mapped[str]
    event_type: Mapped[str]
    error: Mapped[str]


class TrackedRow(Base):
    """A key a run writes to its workspace's tracker by: its claim, and what the write made."""

    __tablename__ = "relayr_tracker_items"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(primary_key=True)
    """What the key names: an `item` or a `comment`."""

    key: Mapped[str] = mapped_column(primary_key=True)
    correlation_id: Mapped[str]
    """The chain of the run that claimed the key first."""

    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    """When the key was last claimed, which a claim with no record goes stale by."""

    ref: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    """The item or comment the key made, once recorded."""

    deleted: Mapped[bool]
    """Whether the item was found deleted."""

    written: Mapped[dict[str, Any]] = mapped_column(JSON)
    """The value relayr last set on each of the item's fields."""


class TrackerFollowerRow(Base):
    """A workspace's tracker follower: its lease, and how far it has read its bound project."""

    __tablename__ = "relayr_tracker_followers"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    project: Mapped[str | None]
    """The tracker project it reads, once it has read it."""

    cursor_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    """The `updated_at` of the last item it read."""

    cursor_id: Mapped[str | None]
    """The tracker's id for the last item it read."""

    swept_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    """When it last read the whole project."""

    holder: Mapped[str | None]
    """Who holds the lease, if anyone does."""

    expires_at: Mapped[datetime | None] = mapped_column(UtcDateTime)
    """When the lease lapses unless it is renewed."""


class SnapshotRow(Base):
    """An item of a bound project: its last snapshot, and relayr's recent writes to it."""

    __tablename__ = "relayr_tracker_snapshots"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    item_id: Mapped[str] = mapped_column(primary_key=True)
    """The tracker's id for the item."""

    item: Mapped[dict[str, Any] | None] = mapped_column(JSON(none_as_null=True))
    """The item as the follower last read it; None until it has."""

    comments_after: Mapped[datetime | None] = mapped_column(UtcDateTime)
    """The comments created before this were read."""

    writes: Mapped[list[str]] = mapped_column(JSON)
    """When relayr wrote to the item within the last while, in UTC, as ISO 8601."""


class TrackerDeadLetterRow(Base):
    """A change in a tracker the follower could not publish."""

    __tablename__ = "relayr_tracker_dead_letters"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    event_id: Mapped[str] = mapped_column(primary_key=True)
    event_type: Mapped[str]
    item_id: Mapped[str]
    error: Mapped[str]
