"""relayr's tables, as SQLAlchemy declarative models.

Table names start with `relayr_`, so they share a database with the application's own tables and
the libraries'.
"""

from datetime import datetime
from typing import Final

from sqlalchemy import BigInteger, DateTime, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

VERSION_TABLE: Final = "relayr_alembic_version"
"""Where Alembic records relayr's schema version, apart from the application's own."""


class Base(DeclarativeBase):
    """The declarative base of relayr's tables."""

    metadata = MetaData(naming_convention={"pk": "pk_%(table_name)s"})


metadata = Base.metadata
"""The schema the migrations build, and that [`create_schema`][relayr.sql.create_schema] creates."""


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

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(primary_key=True)
    """What the key is: a `proposal`, `artifact`, `edit`, `message` or `turn`."""

    key: Mapped[str] = mapped_column(primary_key=True)

    correlation_id: Mapped[str]
    firing_id: Mapped[str]
    run_id: Mapped[str]
    depth: Mapped[int]


class DeadLetterRow(Base):
    """An artifactr envelope the follower could not bridge."""

    __tablename__ = "relayr_dead_letters"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    envelope_id: Mapped[str]
    event_type: Mapped[str]
    error: Mapped[str]
