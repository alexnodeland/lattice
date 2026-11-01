"""The audit log's events: every change to access, and to which integrations are on, typed.

grantr appends one entry per change, in the same transaction as the change, with a sequence
number, the time, the tenant and who made it. Refusals aren't recorded. A key's secret, and its
digest, never are. A read of the log may keep only some types of event, or one subject's
changes (:class:`AuditFilter`).
"""

from collections.abc import Set
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from grantr.core.grants import Grant
from grantr.core.ids import TenantId, UserId, WorkspaceId
from grantr.core.resources import Resource
from grantr.core.roles import Role
from grantr.core.subjects import Member, ServicePrincipal, Subject


class TenantCreated(BaseModel):
    """A tenant was created, with its first owner."""

    model_config = ConfigDict(frozen=True)

    type: Literal["tenant_created"] = "tenant_created"
    owner: UserId


class DeploymentTenantCreated(BaseModel):
    """A tenant was created: the deployment's record of it, beside the tenant's own.

    Its entry is in no tenant's log, the deployment's, and names who created the tenant, so an
    operator who isn't a member of the tenant it created is seen to have created it. The owner is
    a user's id, never an email.
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["deployment_tenant_created"] = "deployment_tenant_created"
    tenant: TenantId
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


class Restricted(BaseModel):
    """A thread or artifact was restricted to those granted a role on it."""

    model_config = ConfigDict(frozen=True)

    type: Literal["restricted"] = "restricted"
    on: Resource


class Unrestricted(BaseModel):
    """A thread or artifact's restriction was lifted: its workspace's roles hold on it again."""

    model_config = ConfigDict(frozen=True)

    type: Literal["unrestricted"] = "unrestricted"
    on: Resource


class IntegrationSet(BaseModel):
    """An integration was turned on or off, on the tenant or in a workspace, or unset."""

    model_config = ConfigDict(frozen=True)

    type: Literal["integration_set"] = "integration_set"
    workspace: WorkspaceId | None
    """The workspace it was set in; ``None`` for the tenant."""

    key: str
    on: bool | None
    """Its new setting; ``None`` for unset, which inherits the level above."""


class SettingSet(BaseModel):
    """A setting was narrowed on the tenant or in a workspace, or unset (lattice ADR-0030)."""

    model_config = ConfigDict(frozen=True)

    type: Literal["setting_set"] = "setting_set"
    workspace: WorkspaceId | None
    """The workspace it was set in; ``None`` for the tenant."""

    key: str
    old: int | list[str] | None
    """Its value before; ``None`` for unset."""

    new: int | list[str] | None
    """Its new value; ``None`` for unset, which inherits the level above."""

    version: int
    """The level's version of the setting once changed: one more than before."""


class ApprovalAsked(BaseModel):
    """A call was deferred for a person's approval (lattice ADR-0035, grantr ADR-0038)."""

    model_config = ConfigDict(frozen=True)

    type: Literal["approval_asked"] = "approval_asked"
    approval: str
    """The approval's id."""

    workspace: WorkspaceId
    capability: str
    """The capability the call would call."""

    caller: str
    """Who called, as ``kind:id``, such as ``run:run_1``."""


class ApprovalAnswered(BaseModel):
    """An approval was answered: the first answer, which settled it."""

    model_config = ConfigDict(frozen=True)

    type: Literal["approval_answered"] = "approval_answered"
    approval: str
    """The approval's id."""

    approved: bool
    surface: str
    """Where it was answered, such as ``portalr``."""


class ApprovalClosed(BaseModel):
    """A pending approval closed unanswered: past its deadline, or withdrawn."""

    model_config = ConfigDict(frozen=True)

    type: Literal["approval_closed"] = "approval_closed"
    approval: str
    """The approval's id."""

    state: Literal["expired", "withdrawn"]
    reason: str


class CapabilityStep(BaseModel):
    """A step of the enforcement path a call passed, or was stopped at (lattice ADR-0037)."""

    model_config = ConfigDict(frozen=True)

    name: str
    """The step, such as ``grant`` or ``approval``."""

    passed: bool
    note: str = ""
    """What it decided, in words, where there is more to say: a taint verdict, an approval's id."""


class CapabilityCalled(BaseModel):
    """A capability was called through lattice-core's enforcer: never its arguments or output.

    Every call leaves one, refused, pending, failed or called (lattice ADR-0037, grantr
    ADR-0039).
    """

    model_config = ConfigDict(frozen=True)

    type: Literal["capability_called"] = "capability_called"
    capability: str
    """The name asked for, such as ``artifactr.edit_text``."""

    version: str | None
    """The version called, or None if no capability of the name was offered."""

    workspace: WorkspaceId
    tenant: str | None = None
    """The tenant the call named, in the deployment's log alone: one that doesn't exist."""

    caller: str
    """Who called, as ``kind:id``, such as ``run:run_1``."""

    client: str | None = None
    """The outside client it came through, by name and connection, if any."""

    correlation_id: str
    """The id of the turn, run or session that made it."""

    surface: str
    arguments_digest: str
    """The digest of its arguments, which an approval binds to."""

    steps: tuple[CapabilityStep, ...]
    """Each step it passed, and the one that stopped it, in order."""

    outcome: Literal["called", "failed", "refused", "pending"]
    approval: str | None = None
    """The approval that let it go ahead, or that it waits for."""

    called_at: datetime
    """When it was called, by the enforcer's clock; the entry's own time is when it was recorded."""


type AuditEvent = Annotated[
    TenantCreated
    | DeploymentTenantCreated
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
    | KeyRevoked
    | Restricted
    | Unrestricted
    | IntegrationSet
    | SettingSet
    | ApprovalAsked
    | ApprovalAnswered
    | ApprovalClosed
    | CapabilityCalled,
    Field(discriminator="type"),
]
"""A change to access, to an integration's setting, to a setting, or to an approval, or a call
of a capability."""


class AuditEntry(BaseModel):
    """An event in the audit log, with its place in it."""

    model_config = ConfigDict(frozen=True)

    seq: int
    """Its place in the deployment's one log, from 1."""

    at: datetime
    tenant: TenantId | None
    """The tenant it changed; ``None`` for the deployment's operators, and a tenant's creation."""

    by: Subject | None
    """Who made the change; ``None`` for the first operator, whom no one granted."""

    event: AuditEvent


type AuditType = Literal[
    "tenant_created",
    "deployment_tenant_created",
    "tenant_deleted",
    "member_added",
    "member_removed",
    "group_defined",
    "group_deleted",
    "role_defined",
    "role_deleted",
    "granted",
    "revoked",
    "key_issued",
    "key_revoked",
    "restricted",
    "unrestricted",
    "integration_set",
    "setting_set",
    "approval_asked",
    "approval_answered",
    "approval_closed",
    "capability_called",
]
"""An audit event's ``type``: what a read of the log may keep."""


@dataclass(frozen=True)
class AuditFilter:
    """Which entries a read of the log keeps: of some types, by one subject, or every one.

    Args:
        types: The event types to keep; every type when empty.
        by: The subject whose changes to keep, such as a user or a rule; anyone's when None.
    """

    types: Set[AuditType] = frozenset()
    by: Subject | None = None

    def keeps(self, entry: AuditEntry) -> bool:
        """Whether an entry passes the filter."""
        return (not self.types or entry.event.type in self.types) and (
            self.by is None or entry.by == self.by
        )
