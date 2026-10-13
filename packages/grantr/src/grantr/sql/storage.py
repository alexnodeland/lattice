"""SQL storage: grantr's tables in a database, through SQLAlchemy's asyncio extension.

It implements the whole :class:`~grantr.grants.Storage` protocol with the same code on
PostgreSQL and SQLite. A transaction locks its tenant's row before it reads anything, so a
tenant's transactions run one at a time, across processes, and so do the deployment's.

Every database call is awaited to its end, even when its caller is cancelled, and the
cancellation is raised after it. SQLAlchemy takes a statement cancelled part-way for a lost
connection, which on SQLite can keep the database's write lock, or the pool's one connection.
"""

import asyncio
import contextlib
import functools
from collections.abc import AsyncGenerator, Awaitable, Callable, Collection
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import CoroutineType
from typing import Any, Final

from pydantic import TypeAdapter
from sqlalchemy import ColumnElement, and_, delete, false, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from grantr.core import (
    EVERY_ENTRY,
    TENANT,
    TENANT_ID,
    AuditEntry,
    AuditEvent,
    AuditFilter,
    Grant,
    Grantee,
    Group,
    Key,
    ListableKind,
    Member,
    Resource,
    Role,
    RulePrincipal,
    ServicePrincipal,
    Subject,
    TenantId,
    User,
    UserId,
    WorkspaceId,
    actor_of,
)
from grantr.sql.tables import (
    DEPLOYMENT,
    AuditRow,
    GrantRow,
    GroupMemberRow,
    GroupRow,
    KeyRow,
    ResourceRow,
    RoleRow,
    TenantRow,
)
from grantr.sql.tenancy import TENANT as TENANT_KEY
from grantr.sql.tenancy import TenantSession

Clock = Callable[[], datetime]
"""Returns the current time; injectable so tests control it."""

_GRANTEE: TypeAdapter[Grantee] = TypeAdapter(Grantee)


def _utc_now() -> datetime:
    return datetime.now(UTC)


# Shared verbatim with artifactr's src/artifactr/sql/storage.py, reflexr's
# src/reflexr/sql/storage.py and relayr's src/relayr/sql/ledger.py; change all four.
async def _to_the_end[T](call: Awaitable[T]) -> T:
    """Await a database call to its end; a cancellation that came meanwhile is raised after."""
    task = asyncio.ensure_future(call)
    cancelled: asyncio.CancelledError | None = None
    while not task.done():
        try:
            await asyncio.wait([task])
        except asyncio.CancelledError as error:
            cancelled = error
    if cancelled is not None:
        if not task.cancelled():
            task.exception()
        raise cancelled
    return task.result()


# Shared verbatim with artifactr's src/artifactr/sql/storage.py, reflexr's
# src/reflexr/sql/storage.py and relayr's src/relayr/sql/ledger.py; change all four.
def _awaited_to_the_end[**P, T](
    method: Callable[P, Awaitable[T]],
) -> Callable[P, "CoroutineType[Any, Any, T]"]:  # subscriptable at run time from Python 3.13
    """Await every call of a method to its end, with :func:`_to_the_end`."""

    @functools.wraps(method)
    async def call(*args: P.args, **kwargs: P.kwargs) -> T:
        return await _to_the_end(method(*args, **kwargs))

    return call


type Columns = tuple[str, str, str]
"""A subject's or resource's kind, workspace and id, with ``""`` for a part it doesn't have."""


def subject_columns(subject: Grantee) -> Columns:
    """The columns a grantee is stored in."""
    if isinstance(subject, RulePrincipal):
        return (subject.kind, subject.workspace, subject.rule)
    return (subject.kind, "", subject.id)


def grantee(kind: str, workspace: str, id: str) -> Grantee:
    """The grantee stored in these columns."""
    if kind == "rule":
        return RulePrincipal(workspace=workspace, rule=id)
    return _GRANTEE.validate_python({"kind": kind, "id": id})


def resource_columns(resource: Resource) -> Columns:
    """The columns a resource is stored in."""
    return (resource.kind, resource.workspace or "", resource.id or "")


def resource(kind: str, workspace: str, id: str) -> Resource:
    """The resource stored in these columns."""
    return Resource.model_validate({"kind": kind, "workspace": workspace or None, "id": id or None})


def _scope(tenant: TenantId | None) -> str:
    """The tenant id rows are stored under: the deployment's for None."""
    if tenant is None:
        return DEPLOYMENT
    if not TENANT_ID.fullmatch(tenant):
        raise ValueError(f"{tenant!r} isn't a tenant id")
    return tenant


def _on(resources: Collection[Resource]) -> ColumnElement[bool]:
    """Grants on any of these resources."""
    return or_(false(), *(_on_one(r) for r in resources))


def _on_one(on: Resource) -> ColumnElement[bool]:
    kind, workspace, id = resource_columns(on)
    return and_(
        GrantRow.resource_kind == kind,
        GrantRow.resource_workspace == workspace,
        GrantRow.resource_id == id,
    )


def _to(subject: Grantee) -> ColumnElement[bool]:
    """Grants made to this grantee."""
    kind, workspace, id = subject_columns(subject)
    return and_(
        GrantRow.subject_kind == kind,
        GrantRow.subject_workspace == workspace,
        GrantRow.subject_id == id,
    )


def _grant(row: GrantRow) -> Grant:
    return Grant(
        tenant=None if row.tenant_id == DEPLOYMENT else row.tenant_id,
        role=row.role,
        on=resource(row.resource_kind, row.resource_workspace, row.resource_id),
        to=grantee(row.subject_kind, row.subject_workspace, row.subject_id),
    )


def _member(kind: str, id: str) -> Member:
    return User(id=id) if kind == "user" else ServicePrincipal(id=id)


def _stored_key(row: KeyRow) -> Key:
    return Key(
        id=row.id,
        tenant=row.tenant_id,
        principal=ServicePrincipal(id=row.principal_id),
        digest=row.digest,
    )


class _Reads:
    """The reads, in one session: a transaction's, or one opened for a single read."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @_awaited_to_the_end
    async def tenant(self, tenant: TenantId) -> bool:
        row = await self._session.get(TenantRow, tenant)
        return row is not None and row.live

    @_awaited_to_the_end
    async def grants(
        self, tenant: TenantId | None, to: Grantee, *, on: Collection[Resource] | None = None
    ) -> list[Grant]:
        scope = _scope(tenant)
        kind, _, id = subject_columns(to)
        groups = select(GroupMemberRow.group_id).where(
            GroupMemberRow.tenant_id == scope,
            GroupMemberRow.member_kind == kind,
            GroupMemberRow.member_id == id,
        )
        in_a_group = and_(GrantRow.subject_kind == "group", GrantRow.subject_id.in_(groups))
        query = select(GrantRow).where(GrantRow.tenant_id == scope, or_(_to(to), in_a_group))
        if on is not None:
            query = query.where(_on(on))
        return [_grant(row) for row in await self._session.scalars(query)]

    @_awaited_to_the_end
    async def has(self, grant: Grant) -> bool:
        key = (
            _scope(grant.tenant),
            *resource_columns(grant.on),
            *subject_columns(grant.to),
            grant.role,
        )
        return await self._session.get(GrantRow, key) is not None

    @_awaited_to_the_end
    async def granted(
        self, tenant: TenantId | None, on: Resource, *, role: str | None = None
    ) -> list[Grant]:
        query = select(GrantRow).where(GrantRow.tenant_id == _scope(tenant), _on_one(on))
        if role is not None:
            query = query.where(GrantRow.role == role)
        return [_grant(row) for row in await self._session.scalars(query)]

    @_awaited_to_the_end
    async def grants_in(
        self, tenant: TenantId, *, workspace: WorkspaceId | None = None
    ) -> list[Grant]:
        query = select(GrantRow).where(GrantRow.tenant_id == tenant)
        if workspace is not None:
            query = query.where(GrantRow.resource_workspace == workspace)
        return [_grant(row) for row in await self._session.scalars(query)]

    @_awaited_to_the_end
    async def roles(self, tenant: TenantId) -> dict[str, Role]:
        rows = await self._session.scalars(select(RoleRow).where(RoleRow.tenant_id == tenant))
        return {row.name: Role(name=row.name, actions=frozenset(row.actions)) for row in rows}

    @_awaited_to_the_end
    async def group(self, tenant: TenantId, group: Group) -> frozenset[Member] | None:
        if await self._session.get(GroupRow, (tenant, group.id)) is None:
            return None
        members = await self._session.execute(
            select(GroupMemberRow.member_kind, GroupMemberRow.member_id).where(
                GroupMemberRow.tenant_id == tenant, GroupMemberRow.group_id == group.id
            )
        )
        return frozenset(_member(kind, id) for kind, id in members)

    @_awaited_to_the_end
    async def groups(self, tenant: TenantId) -> dict[str, frozenset[Member]]:
        groups = await self._session.scalars(
            select(GroupRow.group_id).where(GroupRow.tenant_id == tenant)
        )
        members = await self._session.execute(
            select(
                GroupMemberRow.group_id, GroupMemberRow.member_kind, GroupMemberRow.member_id
            ).where(GroupMemberRow.tenant_id == tenant)
        )
        found: dict[str, set[Member]] = {group: set() for group in groups}
        for group, kind, id in members:
            found[group].add(_member(kind, id))
        return {group: frozenset(members) for group, members in found.items()}

    @_awaited_to_the_end
    async def restricted(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> list[Resource]:
        rows = await self._session.execute(
            select(
                ResourceRow.resource_kind, ResourceRow.resource_workspace, ResourceRow.resource_id
            )
            .where(
                ResourceRow.tenant_id == tenant,
                ResourceRow.restricted,
                *([] if workspace is None else [ResourceRow.resource_workspace == workspace]),
            )
            .order_by(
                ResourceRow.resource_kind, ResourceRow.resource_workspace, ResourceRow.resource_id
            )
        )
        return [resource(*columns) for columns in rows]

    @_awaited_to_the_end
    async def is_restricted(self, tenant: TenantId, on: Resource) -> bool:
        row = await self._session.get(ResourceRow, (tenant, *resource_columns(on)))
        return row is not None and row.restricted

    @_awaited_to_the_end
    async def keys(self, tenant: TenantId) -> list[Key]:
        rows = await self._session.scalars(select(KeyRow).where(KeyRow.tenant_id == tenant))
        return [_stored_key(row) for row in rows]

    @_awaited_to_the_end
    async def resources(self, tenant: TenantId, kind: ListableKind) -> list[Resource]:
        named = await self._session.execute(
            select(GrantRow.resource_kind, GrantRow.resource_workspace, GrantRow.resource_id)
            .where(GrantRow.tenant_id == tenant)
            .union(
                select(
                    ResourceRow.resource_kind,
                    ResourceRow.resource_workspace,
                    ResourceRow.resource_id,
                ).where(ResourceRow.tenant_id == tenant)
            )
        )
        found = frozenset(
            within
            for columns in named
            for within in resource(*columns).chain()
            if within.kind == kind
        )
        return sorted(found, key=lambda found: (found.workspace or "", found.id or ""))


class _Transaction(_Reads):
    """Reads and writes in the session that holds the tenant's lock. Each is awaited to its end."""

    def __init__(self, session: AsyncSession, clock: Clock) -> None:
        super().__init__(session)
        self._clock = clock

    @_awaited_to_the_end
    async def create_tenant(self, tenant: TenantId) -> None:
        await self._session.execute(
            update(TenantRow).where(TenantRow.id == tenant).values(live=True)
        )

    @_awaited_to_the_end
    async def delete_tenant(self, tenant: TenantId) -> None:
        for model in (GrantRow, GroupRow, GroupMemberRow, RoleRow, KeyRow, ResourceRow):
            await self._session.execute(delete(model).where(model.tenant_id == tenant))
        await self._session.execute(
            update(TenantRow).where(TenantRow.id == tenant).values(live=False)
        )

    @_awaited_to_the_end
    async def add_grant(self, grant: Grant) -> None:
        resource_kind, resource_workspace, resource_id = resource_columns(grant.on)
        subject_kind, subject_workspace, subject_id = subject_columns(grant.to)
        self._session.add(
            GrantRow(
                tenant_id=_scope(grant.tenant),
                resource_kind=resource_kind,
                resource_workspace=resource_workspace,
                resource_id=resource_id,
                subject_kind=subject_kind,
                subject_workspace=subject_workspace,
                subject_id=subject_id,
                role=grant.role,
            )
        )
        await self._session.flush()

    @_awaited_to_the_end
    async def remove_grant(self, grant: Grant) -> None:
        await self._session.execute(
            delete(GrantRow).where(
                GrantRow.tenant_id == _scope(grant.tenant),
                _on_one(grant.on),
                _to(grant.to),
                GrantRow.role == grant.role,
            )
        )

    @_awaited_to_the_end
    async def remove_member(self, tenant: TenantId, member: Member) -> None:
        await self._session.execute(
            delete(GrantRow).where(GrantRow.tenant_id == tenant, _to(member))
        )
        await self._session.execute(
            delete(GroupMemberRow).where(
                GroupMemberRow.tenant_id == tenant,
                GroupMemberRow.member_kind == member.kind,
                GroupMemberRow.member_id == member.id,
            )
        )
        if isinstance(member, ServicePrincipal):
            await self._session.execute(
                delete(KeyRow).where(KeyRow.tenant_id == tenant, KeyRow.principal_id == member.id)
            )

    @_awaited_to_the_end
    async def put_group(self, tenant: TenantId, group: Group, members: frozenset[Member]) -> None:
        if await self._session.get(GroupRow, (tenant, group.id)) is None:
            self._session.add(GroupRow(tenant_id=tenant, group_id=group.id))
        await self._session.execute(
            delete(GroupMemberRow).where(
                GroupMemberRow.tenant_id == tenant, GroupMemberRow.group_id == group.id
            )
        )
        self._session.add_all(
            GroupMemberRow(
                tenant_id=tenant, group_id=group.id, member_kind=member.kind, member_id=member.id
            )
            for member in members
        )
        await self._session.flush()

    @_awaited_to_the_end
    async def remove_group(self, tenant: TenantId, group: Group) -> None:
        for statement in (
            delete(GrantRow).where(GrantRow.tenant_id == tenant, _to(group)),
            delete(GroupMemberRow).where(
                GroupMemberRow.tenant_id == tenant, GroupMemberRow.group_id == group.id
            ),
            delete(GroupRow).where(GroupRow.tenant_id == tenant, GroupRow.group_id == group.id),
        ):
            await self._session.execute(statement)

    @_awaited_to_the_end
    async def put_role(self, tenant: TenantId, role: Role) -> None:
        await self._session.merge(
            RoleRow(tenant_id=tenant, name=role.name, actions=sorted(role.actions))
        )
        await self._session.flush()

    @_awaited_to_the_end
    async def remove_role(self, tenant: TenantId, name: str) -> None:
        for statement in (
            delete(GrantRow).where(GrantRow.tenant_id == tenant, GrantRow.role == name),
            delete(RoleRow).where(RoleRow.tenant_id == tenant, RoleRow.name == name),
        ):
            await self._session.execute(statement)

    @_awaited_to_the_end
    async def set_restricted(self, tenant: TenantId, on: Resource, restricted: bool) -> None:
        kind, workspace, id = resource_columns(on)
        await self._session.merge(
            ResourceRow(
                tenant_id=tenant,
                resource_kind=kind,
                resource_workspace=workspace,
                resource_id=id,
                restricted=restricted,
            )
        )
        await self._session.flush()

    @_awaited_to_the_end
    async def add_key(self, key: Key) -> None:
        self._session.add(
            KeyRow(
                id=key.id,
                tenant_id=key.tenant,
                principal_id=key.principal.id,
                digest=key.digest,
            )
        )
        await self._session.flush()

    @_awaited_to_the_end
    async def remove_key(self, tenant: TenantId, key_id: str) -> Key | None:
        row = await self._session.get(KeyRow, key_id)
        if row is None or row.tenant_id != tenant:
            return None
        await self._session.delete(row)
        await self._session.flush()
        return _stored_key(row)

    @_awaited_to_the_end
    async def append(
        self, tenant: TenantId | None, by: Subject | None, event: AuditEvent
    ) -> AuditEntry:
        at = self._clock()
        body = {
            "at": at.isoformat(),
            "by": None if by is None else by.model_dump(mode="json"),
            "event": event.model_dump(mode="json"),
        }
        row = AuditRow(
            tenant_id=_scope(tenant), event_type=event.type, actor=actor_of(by), body=body
        )
        self._session.add(row)
        await self._session.flush()
        return AuditEntry(seq=row.seq, at=at, tenant=tenant, by=by, event=event)


async def _lock(session: AsyncSession, scope: str) -> None:
    """Lock a tenant's row (``SELECT ... FOR UPDATE``), inserting it first if it isn't there."""
    while await session.get(TenantRow, scope, with_for_update=True) is None:
        # A concurrent transaction may insert the row first. Then this insert fails, and the
        # next lookup waits for that transaction to end and locks its row instead.
        with contextlib.suppress(IntegrityError):
            async with session.begin_nested():
                session.add(TenantRow(id=scope, live=False))


ACROSS_TENANTS: Final = frozenset({"tenant_grants", "key", "tenants"})
"""The reads that span tenants, asked before the tenant is known: the only ones that use the
``across_tenants`` engine."""


class SqlStorage:
    """Storage in a SQL database, through SQLAlchemy's asyncio extension.

    Create the tables with :func:`~grantr.sql.migrate` first. The same code runs on
    PostgreSQL (with its default ``READ COMMITTED`` isolation) and on SQLite, whose engines
    must come from :func:`~grantr.sql.create_sqlite_engine`.

    With ``row_level_security``, each transaction tells PostgreSQL its tenant, and the
    policies the migrations create show it only that tenant's rows, and the deployment's
    (:mod:`grantr.sql.tenancy`). The three reads that span tenants, ``ACROSS_TENANTS``, go
    to ``across_tenants`` instead: an engine whose role the policies don't hold, such as the
    tables' owner.

    Args:
        engine: The database to use. The storage does not dispose of it.
        clock: Returns the time each audit entry is stamped with. Defaults to the system
            clock in UTC.
        row_level_security: Whether each transaction names its tenant to PostgreSQL.
        across_tenants: The engine for the reads that span tenants; required with
            ``row_level_security``, and ``engine`` without it.

    Raises:
        ValueError: If ``row_level_security`` is on without ``across_tenants``.
    """

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        clock: Clock = _utc_now,
        row_level_security: bool = False,
        across_tenants: AsyncEngine | None = None,
    ) -> None:
        if row_level_security and across_tenants is None:
            raise ValueError("row-level security needs an engine for the reads across tenants")
        session_class = TenantSession if row_level_security else Session
        self._sessions = async_sessionmaker(
            engine, expire_on_commit=False, sync_session_class=session_class
        )
        self._across = async_sessionmaker(across_tenants or engine, expire_on_commit=False)
        self._clock = clock

    def _session(self, tenant: TenantId | None) -> AsyncSession:
        """A session in a tenant, or on the deployment with None."""
        return self._sessions(info={TENANT_KEY: _scope(tenant)})

    @asynccontextmanager
    async def transaction(self, tenant: TenantId | None) -> AsyncGenerator[_Transaction]:
        """Begin a change; it holds the tenant's row's lock until it ends.

        Closing the session rolls back whatever it did not commit, and returns its connection.
        """
        session = self._session(tenant)
        try:
            await _to_the_end(_lock(session, _scope(tenant)))
            yield _Transaction(session, self._clock)
            await _to_the_end(session.commit())
        finally:
            await _to_the_end(session.close())

    async def _read[T](self, tenant: TenantId | None, read: Callable[[_Reads], Awaitable[T]]) -> T:
        async with self._session(tenant) as session:
            return await read(_Reads(session))

    async def tenant(self, tenant: TenantId) -> bool:
        """Whether the tenant exists."""
        return await self._read(tenant, lambda reads: reads.tenant(tenant))

    async def grants(
        self, tenant: TenantId | None, to: Grantee, *, on: Collection[Resource] | None = None
    ) -> list[Grant]:
        """The grants that apply to a grantee: made to it, or to a group it is in."""
        return await self._read(tenant, lambda reads: reads.grants(tenant, to, on=on))

    async def has(self, grant: Grant) -> bool:
        """Whether this grant was made, exactly."""
        return await self._read(grant.tenant, lambda reads: reads.has(grant))

    async def granted(
        self, tenant: TenantId | None, on: Resource, *, role: str | None = None
    ) -> list[Grant]:
        """Every grant on a resource, to anyone, as it was made; only of one role, if given."""
        return await self._read(tenant, lambda reads: reads.granted(tenant, on, role=role))

    async def grants_in(
        self, tenant: TenantId, *, workspace: WorkspaceId | None = None
    ) -> list[Grant]:
        """Every grant in a tenant, or only those on a workspace and the items in it."""
        return await self._read(tenant, lambda reads: reads.grants_in(tenant, workspace=workspace))

    async def roles(self, tenant: TenantId) -> dict[str, Role]:
        """A tenant's custom roles, by name."""
        return await self._read(tenant, lambda reads: reads.roles(tenant))

    async def group(self, tenant: TenantId, group: Group) -> frozenset[Member] | None:
        """A group's members, or None if there is no such group."""
        return await self._read(tenant, lambda reads: reads.group(tenant, group))

    async def groups(self, tenant: TenantId) -> dict[str, frozenset[Member]]:
        """A tenant's groups, by id, with their members."""
        return await self._read(tenant, lambda reads: reads.groups(tenant))

    async def restricted(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> list[Resource]:
        """The threads and artifacts restricted in a workspace, or in the whole tenant."""
        return await self._read(tenant, lambda reads: reads.restricted(tenant, workspace))

    async def is_restricted(self, tenant: TenantId, on: Resource) -> bool:
        """Whether a thread or artifact is restricted."""
        return await self._read(tenant, lambda reads: reads.is_restricted(tenant, on))

    async def keys(self, tenant: TenantId) -> list[Key]:
        """A tenant's keys."""
        return await self._read(tenant, lambda reads: reads.keys(tenant))

    async def resources(self, tenant: TenantId, kind: ListableKind) -> list[Resource]:
        """The workspaces, threads, artifacts or rules a grant in the tenant names, or is in."""
        return await self._read(tenant, lambda reads: reads.resources(tenant, kind))

    async def tenant_grants(self, user: UserId) -> list[Grant]:
        """The grants on tenants made to a user directly, in every tenant."""
        query = select(GrantRow).where(
            GrantRow.tenant_id != DEPLOYMENT,
            _on_one(TENANT),
            _to(User(id=user)),
        )
        async with self._across() as session:
            return [_grant(row) for row in await _to_the_end(session.scalars(query))]

    async def key(self, key_id: str) -> Key | None:
        """A key, by its public id, in any tenant."""
        async with self._across() as session:
            row = await _to_the_end(session.get(KeyRow, key_id))
            return None if row is None else _stored_key(row)

    async def tenants(self) -> list[TenantId]:
        """Every tenant, in order."""
        async with self._across() as session:
            ids = await _to_the_end(
                session.scalars(select(TenantRow.id).where(TenantRow.live).order_by(TenantRow.id))
            )
            return list(ids)

    async def audit(
        self,
        tenant: TenantId | None,
        *,
        after_seq: int = 0,
        limit: int = 100,
        keep: AuditFilter = EVERY_ENTRY,
    ) -> list[AuditEntry]:
        """A tenant's audit entries after ``after_seq``, in order, or the deployment's with None.

        It returns the first ``limit`` that ``keep`` keeps, found by the type's and the actor's
        indexes.
        """
        query = select(AuditRow).where(
            AuditRow.tenant_id == _scope(tenant), AuditRow.seq > after_seq
        )
        if keep.types:
            query = query.where(AuditRow.event_type.in_(sorted(keep.types)))
        if keep.actor is not None:
            query = query.where(AuditRow.actor == keep.actor)
        query = query.order_by(AuditRow.seq).limit(limit)
        async with self._session(tenant) as session:
            rows = await _to_the_end(session.scalars(query))
            return [
                AuditEntry.model_validate({**row.body, "seq": row.seq, "tenant": tenant})
                for row in rows
            ]
