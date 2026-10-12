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
    Grant,
    Grantee,
    Group,
    Key,
    ListableKind,
    Member,
    Resource,
    Role,
    ServicePrincipal,
    Subject,
    TenantId,
    User,
    UserId,
    WorkspaceId,
)
from grantr.grants.storage import Transaction

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
    items: dict[tuple[TenantId, Resource], bool] = field(
        default_factory=dict[tuple[TenantId, Resource], bool]
    )
    """Every thread and artifact ever restricted, and whether it is now."""
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
        self, tenant: TenantId | None, *, after_seq: int = 0, limit: int = 100
    ) -> list[AuditEntry]:
        """A tenant's audit entries after ``after_seq``, in order, or the deployment's with None."""
        entries = [e for e in self._data.log if e.tenant == tenant and e.seq > after_seq]
        return entries[:limit]
