"""The storage port: where access, integrations' and settings' values, and the audit log live.

It holds tenants, grants, groups, custom roles and keys, and which integrations each tenant and
workspace turned on or off.

grantr ships an in-memory implementation, :class:`~grantr.grants.InMemoryStorage`; the SQL one
comes with grantr's ``sql`` extra. The contract test in the test tree shows what an
implementation must do.

Every read but three is in one tenant, or on the deployment. :meth:`Storage.tenant_grants`,
:meth:`Storage.key` and :meth:`Storage.tenants` span tenants: the first two are asked before the
tenant is known, and the last lists them for operators.
"""

from collections.abc import Collection
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from grantr.core import (
    AuditEntry,
    AuditEvent,
    AuditFilter,
    Grant,
    Grantee,
    Group,
    IntegrationSetting,
    Key,
    ListableKind,
    Member,
    Resource,
    Role,
    SettingRow,
    Subject,
    TenantId,
    UserId,
    WorkspaceId,
)


class Reads(Protocol):
    """What a decision reads: in a transaction, or outside one."""

    async def tenant(self, tenant: TenantId) -> bool:
        """Whether the tenant exists."""
        ...

    async def grants(
        self, tenant: TenantId | None, to: Grantee, *, on: Collection[Resource] | None = None
    ) -> list[Grant]:
        """The grants that apply to a grantee: made to it, or to a group it is in.

        Args:
            tenant: The tenant, or ``None`` for the grants on the deployment.
            to: The grantee. A group is in no group.
            on: Only the grants on these resources; ``None`` for every one.
        """
        ...

    async def has(self, grant: Grant) -> bool:
        """Whether this grant was made, exactly."""
        ...

    async def granted(
        self, tenant: TenantId | None, on: Resource, *, role: str | None = None
    ) -> list[Grant]:
        """Every grant on a resource, to anyone, as it was made; only of one role, if given."""
        ...

    async def grants_in(
        self, tenant: TenantId, *, workspace: WorkspaceId | None = None
    ) -> list[Grant]:
        """Every grant in a tenant, or only those on a workspace and the items in it."""
        ...

    async def roles(self, tenant: TenantId) -> dict[str, Role]:
        """A tenant's custom roles, by name."""
        ...

    async def group(self, tenant: TenantId, group: Group) -> frozenset[Member] | None:
        """A group's members, or None if there is no such group."""
        ...

    async def groups(self, tenant: TenantId) -> dict[str, frozenset[Member]]:
        """A tenant's groups, by id, with their members."""
        ...

    async def keys(self, tenant: TenantId) -> list[Key]:
        """A tenant's keys."""
        ...

    async def resources(self, tenant: TenantId, kind: ListableKind) -> list[Resource]:
        """The workspaces, threads, artifacts or rules grantr knows in the tenant.

        Those a grant names, or is in; and the threads and artifacts ever restricted, and their
        workspaces.
        """
        ...

    async def restricted(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> list[Resource]:
        """The threads and artifacts restricted in a workspace, or in the whole tenant."""
        ...

    async def is_restricted(self, tenant: TenantId, on: Resource) -> bool:
        """Whether a thread or artifact is restricted."""
        ...

    async def integrations(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> dict[str, IntegrationSetting]:
        """The integrations set on a tenant, with None, or in one of its workspaces, by key."""
        ...

    async def settings(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> dict[str, SettingRow]:
        """The settings stored on a tenant, with None, or in one of its workspaces, by key."""
        ...


class Transaction(Reads, Protocol):
    """One atomic change to access, serialized with every other in its tenant.

    It commits when its block exits normally, and leaves nothing behind when it raises.
    """

    async def create_tenant(self, tenant: TenantId) -> None:
        """Register a tenant."""
        ...

    async def delete_tenant(self, tenant: TenantId) -> None:
        """Remove a tenant and everything in it, but its audit log."""
        ...

    async def add_grant(self, grant: Grant) -> None:
        """Store a grant."""
        ...

    async def remove_grant(self, grant: Grant) -> None:
        """Remove a grant."""
        ...

    async def remove_member(self, tenant: TenantId, member: Member) -> None:
        """Remove a member's grants, its places in groups, and its keys."""
        ...

    async def put_group(self, tenant: TenantId, group: Group, members: frozenset[Member]) -> None:
        """Create a group, or replace its members."""
        ...

    async def remove_group(self, tenant: TenantId, group: Group) -> None:
        """Remove a group and its grants."""
        ...

    async def put_role(self, tenant: TenantId, role: Role) -> None:
        """Create a custom role, or replace its actions."""
        ...

    async def remove_role(self, tenant: TenantId, name: str) -> None:
        """Remove a custom role and its grants."""
        ...

    async def set_restricted(self, tenant: TenantId, on: Resource, restricted: bool) -> None:
        """Restrict a thread or artifact, or lift its restriction."""
        ...

    async def set_integration(
        self,
        tenant: TenantId,
        workspace: WorkspaceId | None,
        key: str,
        setting: IntegrationSetting | None,
    ) -> None:
        """Set an integration on a tenant, with None, or in a workspace; unset it with None."""
        ...

    async def set_setting(
        self, tenant: TenantId, workspace: WorkspaceId | None, key: str, row: SettingRow
    ) -> None:
        """Store a setting's row on a tenant, with None, or in a workspace, replacing its last."""
        ...

    async def add_key(self, key: Key) -> None:
        """Store a key."""
        ...

    async def remove_key(self, tenant: TenantId, key_id: str) -> Key | None:
        """Remove one of the tenant's keys, and return it; None if it has no such key."""
        ...

    async def append(
        self, tenant: TenantId | None, by: Subject | None, event: AuditEvent
    ) -> AuditEntry:
        """Append an event to the audit log, with the next sequence number and the time."""
        ...


class Storage(Reads, Protocol):
    """Persistence for grantr: reads, transactions, and the reads that span tenants."""

    def transaction(self, tenant: TenantId | None) -> AbstractAsyncContextManager[Transaction]:
        """Begin a change to one tenant, or to the deployment's operators with ``None``."""
        ...

    async def tenant_grants(self, user: UserId) -> list[Grant]:
        """The grants on tenants made to a user directly, in every tenant."""
        ...

    async def key(self, key_id: str) -> Key | None:
        """A key, by its public id, in any tenant."""
        ...

    async def tenants(self) -> list[TenantId]:
        """Every tenant, in order."""
        ...

    async def audit(
        self,
        tenant: TenantId | None,
        *,
        after_seq: int = 0,
        before_seq: int | None = None,
        limit: int | None = None,
        last: int | None = None,
        keep: AuditFilter | None = None,
    ) -> list[AuditEntry]:
        """A tenant's audit entries in the window ``after_seq < seq < before_seq``, in order.

        The deployment's with None. Of those ``keep`` keeps: the first ``limit``, the last
        ``last``, still oldest first, or every one with neither.
        """
        ...
