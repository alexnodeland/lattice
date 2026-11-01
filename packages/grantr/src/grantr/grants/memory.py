"""In-memory storage, for tests, examples and single-process prototypes.

It implements the whole :class:`~grantr.grants.storage.Storage` protocol, with transactions
that roll back, but keeps nothing across restarts and can't be shared between processes.
"""

import asyncio
from collections.abc import AsyncGenerator, Callable, Collection
from contextlib import asynccontextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from grantr.core import (
    TENANT,
    AuditEntry,
    AuditEvent,
    AuditFilter,
    Connection,
    Grant,
    Grantee,
    Group,
    IntegrationSetting,
    Key,
    ListableKind,
    Member,
    Resource,
    Role,
    ServicePrincipal,
    SettingRow,
    Subject,
    TenantId,
    User,
    UserId,
    WorkspaceId,
)
from grantr.grants.storage import Transaction
from lattice_core.approvals import Approval, ApprovalId
from lattice_core.bindings import Binding, BindingId

Clock = Callable[[], datetime]
"""Returns the current time; injectable so tests control it."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class _Data:
    tenants: frozenset[TenantId] = frozenset()
    grants: frozenset[Grant] = frozenset()
    groups: dict[tuple[TenantId, Group], frozenset[Member]] = field(
        default_factory=dict[tuple[TenantId, Group], frozenset[Member]]
    )
    roles: dict[tuple[TenantId, str], Role] = field(
        default_factory=dict[tuple[TenantId, str], Role]
    )
    keys: dict[str, Key] = field(default_factory=dict[str, Key])
    connections: dict[tuple[TenantId, str], Connection] = field(
        default_factory=dict[tuple[TenantId, str], Connection]
    )
    """Each connection, by tenant and id, in the order made."""
    items: dict[tuple[TenantId, Resource], bool] = field(
        default_factory=dict[tuple[TenantId, Resource], bool]
    )
    """Every thread and artifact ever restricted, and whether it is now."""
    integrations: dict[tuple[TenantId, WorkspaceId | None, str], IntegrationSetting] = field(
        default_factory=dict[tuple[TenantId, WorkspaceId | None, str], IntegrationSetting]
    )
    """Each integration's setting, by tenant, workspace (None for the tenant's) and key."""

    settings: dict[tuple[TenantId, WorkspaceId | None, str], SettingRow] = field(
        default_factory=dict[tuple[TenantId, WorkspaceId | None, str], SettingRow]
    )
    """Each setting's row, by tenant, workspace (None for the tenant's) and key."""
    approvals: dict[tuple[TenantId, ApprovalId], Approval] = field(
        default_factory=dict[tuple[TenantId, ApprovalId], Approval]
    )
    """Each approval as it stands, by tenant and id."""
    bindings: dict[tuple[TenantId, BindingId], Binding] = field(
        default_factory=dict[tuple[TenantId, BindingId], Binding]
    )
    """Each binding, by tenant and id, in the order bound."""
    log: tuple[AuditEntry, ...] = ()


class _Reads:
    """The reads, over whichever data the subclass holds."""

    _data: _Data

    async def tenant(self, tenant: TenantId) -> bool:
        return tenant in self._data.tenants

    async def grants(
        self, tenant: TenantId | None, to: Grantee, *, on: Collection[Resource] | None = None
    ) -> list[Grant]:
        grantees: list[Grantee] = [to]
        if isinstance(to, User | ServicePrincipal):
            grantees += [
                g for (t, g), members in self._data.groups.items() if t == tenant and to in members
            ]
        return [
            grant
            for grant in self._data.grants
            if grant.tenant == tenant and grant.to in grantees and (on is None or grant.on in on)
        ]

    async def has(self, grant: Grant) -> bool:
        return grant in self._data.grants

    async def granted(
        self, tenant: TenantId | None, on: Resource, *, role: str | None = None
    ) -> list[Grant]:
        return [
            grant
            for grant in self._data.grants
            if grant.tenant == tenant and grant.on == on and role in (None, grant.role)
        ]

    async def grants_in(
        self, tenant: TenantId, *, workspace: WorkspaceId | None = None
    ) -> list[Grant]:
        return [
            grant
            for grant in self._data.grants
            if grant.tenant == tenant and workspace in (None, grant.on.workspace)
        ]

    async def roles(self, tenant: TenantId) -> dict[str, Role]:
        return {name: role for (t, name), role in self._data.roles.items() if t == tenant}

    async def group(self, tenant: TenantId, group: Group) -> frozenset[Member] | None:
        return self._data.groups.get((tenant, group))

    async def restricted(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> list[Resource]:
        return sorted(
            (
                item
                for (t, item), restricted in self._data.items.items()
                if t == tenant and workspace in (None, item.workspace) and restricted
            ),
            key=lambda item: (item.kind, item.workspace or "", item.id or ""),
        )

    async def is_restricted(self, tenant: TenantId, on: Resource) -> bool:
        return self._data.items.get((tenant, on), False)

    async def integrations(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> dict[str, IntegrationSetting]:
        return {
            key: setting
            for (t, w, key), setting in self._data.integrations.items()
            if (t, w) == (tenant, workspace)
        }

    async def approval(self, tenant: TenantId, id: ApprovalId) -> Approval | None:
        return self._data.approvals.get((tenant, id))

    async def approvals(
        self,
        tenant: TenantId,
        *,
        workspace: WorkspaceId | None = None,
        due: datetime | None = None,
    ) -> list[Approval]:
        found = [
            approval
            for (t, _), approval in self._data.approvals.items()
            if t == tenant
            and approval.state == "pending"
            and (workspace is None or approval.scope.workspace_id == workspace)
            and (due is None or approval.deadline <= due)
        ]
        return sorted(found, key=lambda approval: (approval.asked_at, approval.id))

    async def bindings(
        self,
        tenant: TenantId,
        *,
        workspace: WorkspaceId | None = None,
        source: str | None = None,
        connection: str | None = None,
    ) -> list[Binding]:
        return [
            binding
            for (t, _), binding in self._data.bindings.items()
            if t == tenant
            and workspace in (None, binding.workspace_id)
            and source in (None, binding.source)
            and connection in (None, binding.connection)
        ]

    async def connections(
        self, tenant: TenantId, *, user: UserId | None = None, client: str | None = None
    ) -> list[Connection]:
        return [
            connection
            for (t, _), connection in self._data.connections.items()
            if t == tenant
            and user in (None, connection.user.id)
            and client in (None, connection.client.client_id)
        ]

    async def connection(self, tenant: TenantId, id: str) -> Connection | None:
        return self._data.connections.get((tenant, id))

    async def settings(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> dict[str, SettingRow]:
        return {
            key: row
            for (t, w, key), row in self._data.settings.items()
            if (t, w) == (tenant, workspace)
        }

    async def groups(self, tenant: TenantId) -> dict[str, frozenset[Member]]:
        return {
            group.id: members for (t, group), members in self._data.groups.items() if t == tenant
        }

    async def keys(self, tenant: TenantId) -> list[Key]:
        return [key for key in self._data.keys.values() if key.tenant == tenant]

    async def resources(self, tenant: TenantId, kind: ListableKind) -> list[Resource]:
        named = frozenset(
            resource
            for on in [
                *(grant.on for grant in self._data.grants if grant.tenant == tenant),
                *(item for t, item in self._data.items if t == tenant),
            ]
            for resource in on.chain()
            if resource.kind == kind
        )
        return sorted(named, key=lambda resource: (resource.workspace or "", resource.id or ""))


class _Transaction(_Reads):
    def __init__(self, data: _Data, clock: Clock) -> None:
        self._data = data
        self._clock = clock

    async def create_tenant(self, tenant: TenantId) -> None:
        self._data = replace(self._data, tenants=self._data.tenants | {tenant})

    async def delete_tenant(self, tenant: TenantId) -> None:
        data = self._data
        self._data = replace(
            data,
            tenants=data.tenants - {tenant},
            grants=frozenset(g for g in data.grants if g.tenant != tenant),
            groups={key: members for key, members in data.groups.items() if key[0] != tenant},
            roles={key: role for key, role in data.roles.items() if key[0] != tenant},
            keys={key_id: key for key_id, key in data.keys.items() if key.tenant != tenant},
            items={key: flag for key, flag in data.items.items() if key[0] != tenant},
            integrations={
                key: setting for key, setting in data.integrations.items() if key[0] != tenant
            },
            settings={key: row for key, row in data.settings.items() if key[0] != tenant},
            approvals={key: a for key, a in data.approvals.items() if key[0] != tenant},
            bindings={key: b for key, b in data.bindings.items() if key[0] != tenant},
            connections={key: c for key, c in data.connections.items() if key[0] != tenant},
        )

    async def add_grant(self, grant: Grant) -> None:
        self._data = replace(self._data, grants=self._data.grants.union((grant,)))

    async def remove_grant(self, grant: Grant) -> None:
        self._data = replace(self._data, grants=self._data.grants.difference((grant,)))

    async def remove_member(self, tenant: TenantId, member: Member) -> None:
        data = self._data
        self._data = replace(
            data,
            grants=frozenset(g for g in data.grants if g.tenant != tenant or g.to != member),
            groups={
                key: members.difference((member,)) if key[0] == tenant else members
                for key, members in data.groups.items()
            },
            keys={
                key_id: key
                for key_id, key in data.keys.items()
                if key.tenant != tenant or key.principal != member
            },
            connections={
                key: connection
                for key, connection in data.connections.items()
                if key[0] != tenant or connection.user != member
            },
        )

    async def put_group(self, tenant: TenantId, group: Group, members: frozenset[Member]) -> None:
        self._data = replace(self._data, groups={**self._data.groups, (tenant, group): members})

    async def remove_group(self, tenant: TenantId, group: Group) -> None:
        data = self._data
        self._data = replace(
            data,
            grants=frozenset(g for g in data.grants if g.tenant != tenant or g.to != group),
            groups={key: members for key, members in data.groups.items() if key != (tenant, group)},
        )

    async def put_role(self, tenant: TenantId, role: Role) -> None:
        self._data = replace(self._data, roles={**self._data.roles, (tenant, role.name): role})

    async def remove_role(self, tenant: TenantId, name: str) -> None:
        data = self._data
        self._data = replace(
            data,
            grants=frozenset(g for g in data.grants if g.tenant != tenant or g.role != name),
            roles={key: role for key, role in data.roles.items() if key != (tenant, name)},
        )

    async def set_restricted(self, tenant: TenantId, on: Resource, restricted: bool) -> None:
        self._data = replace(self._data, items={**self._data.items, (tenant, on): restricted})

    async def set_integration(
        self,
        tenant: TenantId,
        workspace: WorkspaceId | None,
        key: str,
        setting: IntegrationSetting | None,
    ) -> None:
        integrations = dict(self._data.integrations)
        if setting is None:
            integrations.pop((tenant, workspace, key), None)
        else:
            integrations[tenant, workspace, key] = setting
        self._data = replace(self._data, integrations=integrations)

    async def set_setting(
        self, tenant: TenantId, workspace: WorkspaceId | None, key: str, row: SettingRow
    ) -> None:
        self._data = replace(
            self._data, settings={**self._data.settings, (tenant, workspace, key): row}
        )

    async def put_approval(self, approval: Approval) -> None:
        key = (approval.scope.tenant_id, approval.id)
        self._data = replace(self._data, approvals={**self._data.approvals, key: approval})

    async def put_binding(self, binding: Binding) -> None:
        key = (binding.tenant_id, binding.id)
        self._data = replace(self._data, bindings={**self._data.bindings, key: binding})

    async def delete_binding(self, tenant: TenantId, id: BindingId) -> Binding | None:
        found = self._data.bindings.get((tenant, id))
        if found is not None:
            kept = {key: b for key, b in self._data.bindings.items() if key != (tenant, id)}
            self._data = replace(self._data, bindings=kept)
        return found

    async def put_connection(self, connection: Connection) -> None:
        key = (connection.tenant, connection.id)
        self._data = replace(self._data, connections={**self._data.connections, key: connection})

    async def add_key(self, key: Key) -> None:
        self._data = replace(self._data, keys={**self._data.keys, key.id: key})

    async def remove_key(self, tenant: TenantId, key_id: str) -> Key | None:
        key = self._data.keys.get(key_id)
        if key is None or key.tenant != tenant:
            return None
        self._data = replace(
            self._data, keys={k: v for k, v in self._data.keys.items() if k != key_id}
        )
        return key

    def commit(self) -> _Data:
        """What the transaction leaves, to keep if its block exits normally."""
        return self._data

    async def append(
        self, tenant: TenantId | None, by: Subject | None, event: AuditEvent
    ) -> AuditEntry:
        entry = AuditEntry(
            seq=len(self._data.log) + 1, at=self._clock(), tenant=tenant, by=by, event=event
        )
        self._data = replace(self._data, log=(*self._data.log, entry))
        return entry


class InMemoryStorage(_Reads):
    """Storage in this process's memory.

    Args:
        clock: Returns the time each audit entry is stamped with.
    """

    def __init__(self, *, clock: Clock = _utc_now) -> None:
        self._data = _Data()
        self._clock = clock
        self._lock = asyncio.Lock()

    @asynccontextmanager
    async def transaction(self, tenant: TenantId | None) -> AsyncGenerator[Transaction]:
        """Begin a change; one at a time, whatever the tenant."""
        del tenant
        async with self._lock:
            transaction = _Transaction(self._data, self._clock)
            yield transaction
            self._data = transaction.commit()

    async def tenant_grants(self, user: UserId) -> list[Grant]:
        """The grants on tenants made to a user directly, in every tenant."""
        return [
            grant for grant in self._data.grants if grant.on == TENANT and grant.to == User(id=user)
        ]

    async def key(self, key_id: str) -> Key | None:
        """A key, by its public id, in any tenant."""
        return self._data.keys.get(key_id)

    async def tenants(self) -> list[TenantId]:
        """Every tenant, in order."""
        return sorted(self._data.tenants)

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
        entries = [
            e
            for e in self._data.log
            if e.tenant == tenant
            and e.seq > after_seq
            and (before_seq is None or e.seq < before_seq)
            and (keep is None or keep.keeps(e))
        ]
        if last is not None:
            return entries[max(len(entries) - last, 0) :]
        return entries[:limit]
