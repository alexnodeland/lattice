"""artifactr-files' tables, as SQLAlchemy declarative models.

Table names start with `artifactr_files_`, so they share a database with the application's own
tables and the libraries'. Every key starts with the tenant and the workspace, as artifactr's do.
"""

from datetime import UTC, datetime
from typing import Any, Final, override

from sqlalchemy import JSON, BigInteger, DateTime, Dialect, LargeBinary, MetaData, TypeDecorator
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

VERSION_TABLE: Final = "artifactr_files_alembic_version"
"""Where Alembic records artifactr-files' schema version, apart from the application's own."""


class Base(DeclarativeBase):
    """The declarative base of artifactr-files' tables."""

    metadata = MetaData(naming_convention={"pk": "pk_%(table_name)s"})


metadata = Base.metadata
"""The schema the migrations build, and that [`create_schema`][artifactr_files.sql.create_schema]
creates."""


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


class BlobRow(Base):
    """An artifact's bytes, by their digest."""

    __tablename__ = "artifactr_files_blobs"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    artifact_id: Mapped[str] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(primary_key=True)
    size: Mapped[int] = mapped_column(BigInteger)
    data: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    """The bytes: `bytea` on PostgreSQL, stored `EXTERNAL`, since zipped formats don't compress.
    Loaded only when asked for, so that putting bytes already there doesn't read them."""

    last_put: Mapped[datetime] = mapped_column(UtcDateTime)
    """When the bytes were last put, which collection keeps them for a while after."""


class CheckoutRow(Base):
    """A check-out of a native file."""

    __tablename__ = "artifactr_files_checkouts"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    workspace_id: Mapped[str] = mapped_column(primary_key=True)
    id: Mapped[str] = mapped_column(primary_key=True)
    artifact_id: Mapped[str]
    base_version: Mapped[int] = mapped_column(BigInteger)
    base_sha256: Mapped[str]
    actor: Mapped[dict[str, Any]] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    checked_in: Mapped[bool]
