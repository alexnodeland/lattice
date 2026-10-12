"""The audit log's events: every change to access, typed.

grantr appends one entry per change, in the same transaction as the change, with a sequence
number, the time, the tenant and who made it. Refusals aren't recorded. A key's secret, and its
digest, never are.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from grantr.core.grants import Grant
from grantr.core.ids import TenantId, UserId
from grantr.core.roles import Role
from grantr.core.subjects import Member, ServicePrincipal, Subject


class TenantCreated(BaseModel):
    """A tenant was created, with its first owner."""

    model_config = ConfigDict(frozen=True)

    type: Literal["tenant_created"] = "tenant_created"
    owner: UserId


class TenantDeleted(BaseModel):
    """A tenant was deleted, with everything grantr held for it but its audit log."""

    model_config = ConfigDict(frozen=True)

    type: Literal["tenant_deleted"] = "tenant_deleted"


class MemberAdded(BaseModel):
    """A user or service principal joined the tenant."""

    model_config = ConfigDict(frozen=True)

    type: Literal["member_added"] = "member_added"
    member: Member


class MemberRemoved(BaseModel):
    """A member left the tenant, with its grants, its places in groups, and its keys."""

    model_config = ConfigDict(frozen=True)

    type: Literal["member_removed"] = "member_removed"
    member: Member


class GroupDefined(BaseModel):
    """A group was created, or its members replaced."""

    model_config = ConfigDict(frozen=True)

    type: Literal["group_defined"] = "group_defined"
    group: str
    members: frozenset[Member]


class GroupDeleted(BaseModel):
    """A group was deleted, with its grants."""

    model_config = ConfigDict(frozen=True)

    type: Literal["group_deleted"] = "group_deleted"
    group: str


class RoleDefined(BaseModel):
    """A custom role was created, or its actions replaced."""

    model_config = ConfigDict(frozen=True)

    type: Literal["role_defined"] = "role_defined"
    role: Role


class RoleDeleted(BaseModel):
    """A custom role was deleted, with its grants."""

    model_config = ConfigDict(frozen=True)

    type: Literal["role_deleted"] = "role_deleted"
    role: str


class Granted(BaseModel):
    """A role was granted."""

    model_config = ConfigDict(frozen=True)

    type: Literal["granted"] = "granted"
    grant: Grant


class Revoked(BaseModel):
    """A grant was revoked."""

    model_config = ConfigDict(frozen=True)

    type: Literal["revoked"] = "revoked"
    grant: Grant


class KeyIssued(BaseModel):
    """A key was issued to a service principal."""

    model_config = ConfigDict(frozen=True)

    type: Literal["key_issued"] = "key_issued"
    principal: ServicePrincipal
    key: str
    """The key's public id."""


class KeyRevoked(BaseModel):
    """A key was revoked."""

    model_config = ConfigDict(frozen=True)

    type: Literal["key_revoked"] = "key_revoked"
    principal: ServicePrincipal
    key: str


type AuditEvent = Annotated[
    TenantCreated
    | TenantDeleted
    | MemberAdded
    | MemberRemoved
    | GroupDefined
    | GroupDeleted
    | RoleDefined
    | RoleDeleted
    | Granted
    | Revoked
    | KeyIssued
    | KeyRevoked,
    Field(discriminator="type"),
]
"""A change to access."""


class AuditEntry(BaseModel):
    """An event in the audit log, with its place in it."""

    model_config = ConfigDict(frozen=True)

    seq: int
    """Its place in the deployment's one log, from 1."""

    at: datetime
    tenant: TenantId | None
    """The tenant it changed; ``None`` for the deployment's operators."""

    by: Subject | None
    """Who made the change; ``None`` for the first operator, whom no one granted."""

    event: AuditEvent
