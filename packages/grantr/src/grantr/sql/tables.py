"""grantr's tables, as SQLAlchemy declarative models.

Table names start with ``grantr_`` so they share a database with the application's own tables
and the libraries'. Every row is in a tenant; the deployment's rows (its operators' grants and
their audit entries) are in :data:`DEPLOYMENT`, which no tenant id can be. A subject and a
resource are stored in typed columns, their kind, workspace and id, with an empty string for a
part they don't have, so every primary key is free of nulls.
"""

from typing import Any, Final

from sqlalchemy import JSON, BigInteger, Index, Integer, MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

VERSION_TABLE: Final = "grantr_alembic_version"
"""Where Alembic records grantr's schema version, apart from the application's own."""

DEPLOYMENT: Final = "~deployment"
"""The tenant id of the deployment's rows, which no tenant can take: a tenant id has no ``~``."""


class Base(DeclarativeBase):
    """The declarative base of grantr's tables."""

    metadata = MetaData(naming_convention={"pk": "pk_%(table_name)s"})


metadata = Base.metadata
"""The schema the migrations build, and that :func:`grantr.sql.create_schema` creates."""


class TenantRow(Base):
    """A tenant, or the deployment: the row each transaction in it locks."""

    __tablename__ = "grantr_tenants"

    id: Mapped[str] = mapped_column(primary_key=True)
    live: Mapped[bool]
    """Whether the tenant exists. A row is locked before it exists, and outlives its tenant."""


class GrantRow(Base):
    """A grant. Its primary key leads with the tenant and the resource: a check's index."""

    __tablename__ = "grantr_grants"
    __table_args__ = (
        Index("ix_grantr_grants_subject", "subject_kind", "subject_id", "tenant_id"),
        Index("ix_grantr_grants_workspace", "tenant_id", "resource_workspace"),
    )

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    resource_kind: Mapped[str] = mapped_column(primary_key=True)
    resource_workspace: Mapped[str] = mapped_column(primary_key=True)
    resource_id: Mapped[str] = mapped_column(primary_key=True)
    subject_kind: Mapped[str] = mapped_column(primary_key=True)
    subject_workspace: Mapped[str] = mapped_column(primary_key=True)
    """A rule's workspace; empty for every other subject."""

    subject_id: Mapped[str] = mapped_column(primary_key=True)
    """A user's, service principal's or group's id, or a rule's name."""

    role: Mapped[str] = mapped_column(primary_key=True)


class ResourceRow(Base):
    """A thread or artifact grantr knows because it was restricted, and whether it is now."""

    __tablename__ = "grantr_resources"
    __table_args__ = (
        Index("ix_grantr_resources_restricted", "tenant_id", "resource_workspace", "restricted"),
    )

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    resource_kind: Mapped[str] = mapped_column(primary_key=True)
    resource_workspace: Mapped[str] = mapped_column(primary_key=True)
    resource_id: Mapped[str] = mapped_column(primary_key=True)
    restricted: Mapped[bool]


class GroupRow(Base):
    """A group, which exists even with no members."""

    __tablename__ = "grantr_groups"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    group_id: Mapped[str] = mapped_column(primary_key=True)


class GroupMemberRow(Base):
    """A member of a group: a user or a service principal."""

    __tablename__ = "grantr_group_members"
    __table_args__ = (
        Index("ix_grantr_group_members_member", "tenant_id", "member_kind", "member_id"),
    )

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    group_id: Mapped[str] = mapped_column(primary_key=True)
    member_kind: Mapped[str] = mapped_column(primary_key=True)
    member_id: Mapped[str] = mapped_column(primary_key=True)


class RoleRow(Base):
    """A tenant's custom role."""

    __tablename__ = "grantr_roles"

    tenant_id: Mapped[str] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(primary_key=True)
    actions: Mapped[list[str]] = mapped_column(JSON)


class KeyRow(Base):
    """A service principal's key: its id, and its secret's digest, never the secret."""

    __tablename__ = "grantr_keys"
    __table_args__ = (Index("ix_grantr_keys_tenant", "tenant_id"),)

    id: Mapped[str] = mapped_column(primary_key=True)
    tenant_id: Mapped[str]
    principal_id: Mapped[str]
    """The service principal's id."""

    digest: Mapped[str]


class AuditRow(Base):
    """An audit entry: its sequence number, tenant, event type and maker, and the rest as JSON.

    A read filters by the type and the maker.
    """

    __tablename__ = "grantr_audit"
    __table_args__ = (
        Index("ix_grantr_audit_tenant", "tenant_id", "seq"),
        Index("ix_grantr_audit_type", "tenant_id", "event_type", "seq"),
        Index("ix_grantr_audit_actor", "tenant_id", "actor", "seq"),
    )

    # SQLite numbers only an INTEGER primary key itself.
    seq: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer(), "sqlite"), primary_key=True, autoincrement=True
    )
    tenant_id: Mapped[str]
    event_type: Mapped[str]
    """The event's ``type``."""

    actor: Mapped[str | None]
    """Who made it, as :func:`~grantr.core.actor_of` names them; null for the first operator."""

    body: Mapped[dict[str, Any]] = mapped_column(JSON)
    """The entry's time, maker and event."""
