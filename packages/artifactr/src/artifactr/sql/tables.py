"""artifactr's tables, as SQLAlchemy declarative models.

Every table's primary key starts with the tenant and the workspace, so every row belongs to one
tenant's workspace and every query is scoped by it (ADR-0011). Entities are stored as the JSON
of their Pydantic models, next to the columns that reads filter and order by. The type is
``JSON`` everywhere, not PostgreSQL's ``JSONB``, which would reorder the keys of dicts in
artifact data. Table names start with ``artifactr_`` so they can share a database with the
application's own tables.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, BigInteger, DateTime, Index, LargeBinary, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

VERSION_TABLE = "artifactr_alembic_version"
"""Where Alembic records artifactr's schema version, apart from the application's own."""


class Base(DeclarativeBase):
    """The declarative base of artifactr's tables."""

    metadata = MetaData(naming_convention={"pk": "pk_%(table_name)s"})


metadata = Base.metadata
"""The schema the migrations build, and that :func:`artifactr.sql.create_schema` creates."""


class ScopedRow(Base):
    """A row that belongs to one tenant's workspace."""

    __abstract__ = True

    # Negative sort orders put these columns first, so they lead every primary key and a
    # workspace's rows are one range of its index.
    tenant_id: Mapped[str] = mapped_column(primary_key=True, sort_order=-3)
    workspace_id: Mapped[str] = mapped_column(primary_key=True, sort_order=-2)


class WorkspaceRow(ScopedRow):
    """A workspace: the row every transaction locks, and its counters."""

    __tablename__ = "artifactr_workspaces"

    head_seq: Mapped[int] = mapped_column(BigInteger)
    """The ``seq`` of the log's latest envelope, or 0."""

    last_position: Mapped[int] = mapped_column(BigInteger)
    """The position given to the most recently created row, or 0."""


class EntityRow(ScopedRow):
    """An entity that is replaced as it changes, and listed in the order it was created."""

    __abstract__ = True

    id: Mapped[str] = mapped_column(primary_key=True, sort_order=-1)
    position: Mapped[int] = mapped_column(BigInteger, sort_order=-1)
    """Creation order within the workspace, from :attr:`WorkspaceRow.last_position`."""

    @declared_attr.directive
    @classmethod
    def __table_args__(cls) -> tuple[Index]:
        return (Index(f"ix_{cls.__tablename__}_position", "tenant_id", "workspace_id", "position"),)


class ArtifactRow(EntityRow):
    """An artifact's current version."""

    __tablename__ = "artifactr_artifacts"

    kind: Mapped[str]
    version: Mapped[int]
    archived: Mapped[bool]
    data: Mapped[dict[str, Any]] = mapped_column(JSON)
    updated_by: Mapped[Any] = mapped_column(JSON)
    """The actor as JSON, validated into an ``Actor`` by ``load_versioned``."""


class RevisionRow(ScopedRow):
    """One immutable version of an artifact."""

    __tablename__ = "artifactr_revisions"

    artifact_id: Mapped[str] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class ProposalRow(EntityRow):
    """A proposal."""

    __tablename__ = "artifactr_proposals"

    status: Mapped[str]
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class ThreadRow(EntityRow):
    """A thread."""

    __tablename__ = "artifactr_threads"

    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class RunRow(EntityRow):
    """An agent run."""

    __tablename__ = "artifactr_runs"

    thread_id: Mapped[str]
    status: Mapped[str]
    body: Mapped[dict[str, Any]] = mapped_column(JSON)


class EventRow(ScopedRow):
    """One envelope in a workspace's log."""

    __tablename__ = "artifactr_events"

    seq: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    envelope: Mapped[dict[str, Any]] = mapped_column(JSON)


class HistoryRow(ScopedRow):
    """A chunk of a thread's serialized model messages."""

    __tablename__ = "artifactr_history"
    __table_args__ = (
        Index("ix_artifactr_history_thread", "tenant_id", "workspace_id", "thread_id", "position"),
    )

    position: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    thread_id: Mapped[str]
    seq: Mapped[int] = mapped_column(BigInteger)
    """The log's head when the chunk was saved."""
    messages: Mapped[bytes] = mapped_column(LargeBinary)


class LeaseRow(ScopedRow):
    """An exclusive, expiring claim on a key, such as a thread."""

    __tablename__ = "artifactr_leases"

    key: Mapped[str] = mapped_column(primary_key=True)
    holder: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
