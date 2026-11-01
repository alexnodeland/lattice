"""SQL storage: grantr's tables in a database, through SQLAlchemy's asyncio extension.

It implements the whole :class:`~grantr.grants.Storage` protocol with the same code on
PostgreSQL and SQLite. A transaction locks its tenant's row before it reads anything, so a
tenant's transactions run one at a time, across processes, and so do the deployment's.

Every database call is awaited to its end, even when its caller is cancelled, and the
cancellation is raised after it. SQLAlchemy takes a statement cancelled part-way for a lost
connection, which on SQLite can keep the database's write lock, or the pool's one connection.
"""

from collections.abc import AsyncGenerator, Awaitable, Callable, Collection
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Final

from pydantic import TypeAdapter
from sqlalchemy import ColumnElement, Select, and_, delete, false, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session

from grantr.core import (
    TENANT,
    TENANT_ID,
    Agent,
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
    RulePrincipal,
    ServicePrincipal,
    SettingRow,
    Subject,
    TenantId,
    User,
    UserId,
    WorkspaceId,
)
from grantr.sql.tables import (
    DEPLOYMENT,
    ApprovalRow,
    AuditRow,
    BindingRow,
    ConnectionRow,
    GrantRow,
    GroupMemberRow,
    GroupRow,
    IntegrationRow,
    KeyRow,
    ResourceRow,
    RoleRow,
    SettingRowRecord,
    TenantRow,
)
from lattice_core.approvals import Approval, ApprovalId
from lattice_core.bindings import Binding, BindingId
from lattice_core.sql.sessions import awaited_to_the_end, lock_row, to_the_end
from lattice_core.sql.tenancy import TENANT_KEY, TenantSession

Clock = Callable[[], datetime]
"""Returns the current time; injectable so tests control it."""

_GRANTEE: TypeAdapter[Grantee] = TypeAdapter(Grantee)


def _utc_now() -> datetime:
    return datetime.now(UTC)


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


def actor_columns(by: Subject | None) -> Columns:
    """The columns an audit entry's maker is stored in: a subject's, or none for no one."""
    match by:
        case None:
            return ("", "", "")
        case Agent():
            return (by.kind, "", "")
        case _:
            return subject_columns(by)


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

    @awaited_to_the_end
    async def tenant(self, tenant: TenantId) -> bool:
        row = await self._session.get(TenantRow, tenant)
        return row is not None and row.live

    @awaited_to_the_end
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

    @awaited_to_the_end
    async def has(self, grant: Grant) -> bool:
        key = (
            _scope(grant.tenant),
            *resource_columns(grant.on),
            *subject_columns(grant.to),
            grant.role,
        )
        return await self._session.get(GrantRow, key) is not None

    @awaited_to_the_end
    async def granted(
        self, tenant: TenantId | None, on: Resource, *, role: str | None = None
    ) -> list[Grant]:
        query = select(GrantRow).where(GrantRow.tenant_id == _scope(tenant), _on_one(on))
        if role is not None:
            query = query.where(GrantRow.role == role)
        return [_grant(row) for row in await self._session.scalars(query)]

    @awaited_to_the_end
    async def grants_in(
        self, tenant: TenantId, *, workspace: WorkspaceId | None = None
    ) -> list[Grant]:
        query = select(GrantRow).where(GrantRow.tenant_id == tenant)
        if workspace is not None:
            query = query.where(GrantRow.resource_workspace == workspace)
        return [_grant(row) for row in await self._session.scalars(query)]

    @awaited_to_the_end
    async def roles(self, tenant: TenantId) -> dict[str, Role]:
        rows = await self._session.scalars(select(RoleRow).where(RoleRow.tenant_id == tenant))
        return {row.name: Role(name=row.name, actions=frozenset(row.actions)) for row in rows}

    @awaited_to_the_end
    async def group(self, tenant: TenantId, group: Group) -> frozenset[Member] | None:
        if await self._session.get(GroupRow, (tenant, group.id)) is None:
            return None
        members = await self._session.execute(
            select(GroupMemberRow.member_kind, GroupMemberRow.member_id).where(
                GroupMemberRow.tenant_id == tenant, GroupMemberRow.group_id == group.id
            )
        )
        return frozenset(_member(kind, id) for kind, id in members)

    @awaited_to_the_end
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

    @awaited_to_the_end
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

    @awaited_to_the_end
    async def is_restricted(self, tenant: TenantId, on: Resource) -> bool:
        row = await self._session.get(ResourceRow, (tenant, *resource_columns(on)))
        return row is not None and row.restricted

    @awaited_to_the_end
    async def integrations(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> dict[str, IntegrationSetting]:
        rows = await self._session.scalars(
            select(IntegrationRow).where(
                IntegrationRow.tenant_id == tenant, IntegrationRow.workspace == (workspace or "")
            )
        )
        return {row.key: IntegrationSetting.model_validate(row.setting) for row in rows}

    @awaited_to_the_end
    async def approval(self, tenant: TenantId, id: ApprovalId) -> Approval | None:
        row = await self._session.get(ApprovalRow, (tenant, id))
        return None if row is None else Approval.model_validate(row.approval)

    @awaited_to_the_end
    async def approvals(
        self,
        tenant: TenantId,
        *,
        workspace: WorkspaceId | None = None,
        due: datetime | None = None,
    ) -> list[Approval]:
        query = select(ApprovalRow).where(
            ApprovalRow.tenant_id == tenant, ApprovalRow.state == "pending"
        )
        if workspace is not None:
            query = query.where(ApprovalRow.workspace == workspace)
        found = [
            Approval.model_validate(row.approval) for row in await self._session.scalars(query)
        ]
        # The deadline and the time asked are compared as times, not as each database's text.
        return sorted(
            (a for a in found if due is None or a.deadline <= due),
            key=lambda approval: (approval.asked_at, approval.id),
        )

    @awaited_to_the_end
    async def bindings(
        self,
        tenant: TenantId,
        *,
        workspace: WorkspaceId | None = None,
        source: str | None = None,
        connection: str | None = None,
    ) -> list[Binding]:
        query = select(BindingRow).where(BindingRow.tenant_id == tenant)
        if workspace is not None:
            query = query.where(BindingRow.workspace == workspace)
        if source is not None:
            query = query.where(BindingRow.source == source)
        if connection is not None:
            query = query.where(BindingRow.connection == connection)
        found = [Binding.model_validate(row.binding) for row in await self._session.scalars(query)]
        return sorted(found, key=lambda binding: (binding.bound_at, binding.id))

    @awaited_to_the_end
    async def connections(
        self, tenant: TenantId, *, user: UserId | None = None, client: str | None = None
    ) -> list[Connection]:
        query = select(ConnectionRow).where(ConnectionRow.tenant_id == tenant)
        if user is not None:
            query = query.where(ConnectionRow.user_id == user)
        if client is not None:
            query = query.where(ConnectionRow.client_id == client)
        rows = await self._session.scalars(query)
        found = [Connection.model_validate(row.connection) for row in rows]
        return sorted(found, key=lambda connection: (connection.created_at, connection.id))

    @awaited_to_the_end
    async def connection(self, tenant: TenantId, id: str) -> Connection | None:
        row = await self._session.get(ConnectionRow, (tenant, id))
        return None if row is None else Connection.model_validate(row.connection)

    @awaited_to_the_end
    async def settings(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> dict[str, SettingRow]:
        rows = await self._session.scalars(
            select(SettingRowRecord).where(
                SettingRowRecord.tenant_id == tenant,
                SettingRowRecord.workspace == (workspace or ""),
            )
        )
        return {
            row.key: SettingRow.model_validate(
                {
                    **row.written,
                    "value": row.value,
                    "version": row.version,
                    "profile_version": row.profile_version,
                }
            )
            for row in rows
        }

    @awaited_to_the_end
    async def keys(self, tenant: TenantId) -> list[Key]:
        rows = await self._session.scalars(select(KeyRow).where(KeyRow.tenant_id == tenant))
        return [_stored_key(row) for row in rows]

    @awaited_to_the_end
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

    @awaited_to_the_end
    async def create_tenant(self, tenant: TenantId) -> None:
        await self._session.execute(
            update(TenantRow).where(TenantRow.id == tenant).values(live=True)
        )

    @awaited_to_the_end
    async def delete_tenant(self, tenant: TenantId) -> None:
        for model in (
            GrantRow,
            GroupRow,
            GroupMemberRow,
            RoleRow,
            KeyRow,
            ResourceRow,
            IntegrationRow,
            SettingRowRecord,
            ApprovalRow,
            BindingRow,
            ConnectionRow,
        ):
            await self._session.execute(delete(model).where(model.tenant_id == tenant))
        await self._session.execute(
            update(TenantRow).where(TenantRow.id == tenant).values(live=False)
        )

    @awaited_to_the_end
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

    @awaited_to_the_end
    async def remove_grant(self, grant: Grant) -> None:
        await self._session.execute(
            delete(GrantRow).where(
                GrantRow.tenant_id == _scope(grant.tenant),
                _on_one(grant.on),
                _to(grant.to),
                GrantRow.role == grant.role,
            )
        )

    @awaited_to_the_end
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
        else:
            await self._session.execute(
                delete(ConnectionRow).where(
                    ConnectionRow.tenant_id == tenant, ConnectionRow.user_id == member.id
                )
            )

    @awaited_to_the_end
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

    @awaited_to_the_end
    async def remove_group(self, tenant: TenantId, group: Group) -> None:
        for statement in (
            delete(GrantRow).where(GrantRow.tenant_id == tenant, _to(group)),
            delete(GroupMemberRow).where(
                GroupMemberRow.tenant_id == tenant, GroupMemberRow.group_id == group.id
            ),
            delete(GroupRow).where(GroupRow.tenant_id == tenant, GroupRow.group_id == group.id),
        ):
            await self._session.execute(statement)

    @awaited_to_the_end
    async def put_role(self, tenant: TenantId, role: Role) -> None:
        await self._session.merge(
            RoleRow(tenant_id=tenant, name=role.name, actions=sorted(role.actions))
        )
        await self._session.flush()

    @awaited_to_the_end
    async def remove_role(self, tenant: TenantId, name: str) -> None:
        for statement in (
            delete(GrantRow).where(GrantRow.tenant_id == tenant, GrantRow.role == name),
            delete(RoleRow).where(RoleRow.tenant_id == tenant, RoleRow.name == name),
        ):
            await self._session.execute(statement)

    @awaited_to_the_end
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

    @awaited_to_the_end
    async def set_integration(
        self,
        tenant: TenantId,
        workspace: WorkspaceId | None,
        key: str,
        setting: IntegrationSetting | None,
    ) -> None:
        if setting is None:
            await self._session.execute(
                delete(IntegrationRow).where(
                    IntegrationRow.tenant_id == tenant,
                    IntegrationRow.workspace == (workspace or ""),
                    IntegrationRow.key == key,
                )
            )
            return
        await self._session.merge(
            IntegrationRow(
                tenant_id=tenant,
                workspace=workspace or "",
                key=key,
                setting=setting.model_dump(mode="json"),
            )
        )

    @awaited_to_the_end
    async def put_approval(self, approval: Approval) -> None:
        await self._session.merge(
            ApprovalRow(
                tenant_id=approval.scope.tenant_id,
                id=approval.id,
                workspace=approval.scope.workspace_id,
                state=approval.state,
                approval=approval.model_dump(mode="json"),
            )
        )

    @awaited_to_the_end
    async def put_binding(self, binding: Binding) -> None:
        self._session.add(
            BindingRow(
                tenant_id=binding.tenant_id,
                id=binding.id,
                workspace=binding.workspace_id,
                source=binding.source,
                connection=binding.connection,
                binding=binding.model_dump(mode="json"),
            )
        )
        await self._session.flush()

    @awaited_to_the_end
    async def delete_binding(self, tenant: TenantId, id: BindingId) -> Binding | None:
        row = await self._session.get(BindingRow, (tenant, id))
        if row is None:
            return None
        await self._session.delete(row)
        await self._session.flush()
        return Binding.model_validate(row.binding)

    @awaited_to_the_end
    async def put_connection(self, connection: Connection) -> None:
        await self._session.merge(
            ConnectionRow(
                tenant_id=connection.tenant,
                id=connection.id,
                user_id=connection.user.id,
                client_id=connection.client.client_id,
                connection=connection.model_dump(mode="json"),
            )
        )
        await self._session.flush()

    @awaited_to_the_end
    async def set_setting(
        self, tenant: TenantId, workspace: WorkspaceId | None, key: str, row: SettingRow
    ) -> None:
        await self._session.merge(
            SettingRowRecord(
                tenant_id=tenant,
                workspace=workspace or "",
                key=key,
                value=row.value,
                version=row.version,
                written=row.model_dump(mode="json", include={"by", "at"}),
                profile_version=row.profile_version,
            )
        )
        await self._session.flush()

    @awaited_to_the_end
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

    @awaited_to_the_end
    async def remove_key(self, tenant: TenantId, key_id: str) -> Key | None:
        row = await self._session.get(KeyRow, key_id)
        if row is None or row.tenant_id != tenant:
            return None
        await self._session.delete(row)
        await self._session.flush()
        return _stored_key(row)

    @awaited_to_the_end
    async def append(
        self, tenant: TenantId | None, by: Subject | None, event: AuditEvent
    ) -> AuditEntry:
        at = self._clock()
        body = {
            "at": at.isoformat(),
            "by": None if by is None else by.model_dump(mode="json"),
            "event": event.model_dump(mode="json"),
        }
        actor_kind, actor_workspace, actor_id = actor_columns(by)
        row = AuditRow(
            seq=await self._next_seq(_scope(tenant)),
            tenant_id=_scope(tenant),
            event_type=event.type,
            actor_kind=actor_kind,
            actor_workspace=actor_workspace,
            actor_id=actor_id,
            body=body,
        )
        self._session.add(row)
        await self._session.flush()
        return AuditEntry(seq=row.seq, at=at, tenant=tenant, by=by, event=event)

    async def _next_seq(self, scope: str) -> int | None:
        """The sequence number of a row of another scope than the transaction's, on PostgreSQL.

        A tenant's transaction adds the deployment log's entry of the tenant's creation, which
        its policy lets it insert but not read back. ``INSERT ... RETURNING`` reads the new row
        through the read policy, so it names the number itself, from the table's own sequence,
        after taking the deployment log's lock, which every writer of the deployment's entries
        holds until it commits: the numbers of the deployment's log are taken, and commit, in
        order. Any other row takes the number the insert returns.
        """
        if scope == self._session.info.get(TENANT_KEY):
            return None
        if not await _serialize_deployment_log(self._session):
            return None
        return await self._session.scalar(
            select(func.nextval(func.pg_get_serial_sequence(AuditRow.__tablename__, "seq")))
        )


async def _serialize_deployment_log(session: AsyncSession) -> bool:
    """Take the lock every writer of the deployment log's entries holds until it commits.

    It is a transaction-scoped advisory lock, which row-level security does not apply to, on a
    hash of the current schema and the audit table. The key only has to be the same for every
    connection of a running deployment; a hash that another schema's shared would only serialize
    the two. It is always taken after the tenant's row lock, so two transactions never wait on
    each other's. Returns whether it was taken: only on PostgreSQL.
    """
    if (await session.connection()).dialect.name != "postgresql":
        return False
    await session.execute(
        select(
            func.pg_advisory_xact_lock(
                func.hashtextextended(func.current_schema() + "." + AuditRow.__tablename__, 0)
            )
        )
    )
    return True


async def _lock(session: AsyncSession, scope: str) -> None:
    """Lock a tenant's row, which is not live until the tenant is created."""
    await lock_row(session, TenantRow, scope, TenantRow(id=scope, live=False))


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

        A change to the deployment also takes the deployment log's lock, after it, as a tenant's
        creation does when it adds its entry there: the lock order is always the tenant's, then
        the log's.

        Closing the session rolls back whatever it did not commit, and returns its connection.
        """
        session = self._session(tenant)
        try:
            await to_the_end(_lock(session, _scope(tenant)))
            if tenant is None:
                await to_the_end(_serialize_deployment_log(session))
            yield _Transaction(session, self._clock)
            await to_the_end(session.commit())
        finally:
            await to_the_end(session.close())

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

    async def integrations(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> dict[str, IntegrationSetting]:
        """The integrations set on a tenant, with None, or in one of its workspaces, by key."""
        return await self._read(tenant, lambda reads: reads.integrations(tenant, workspace))

    async def settings(
        self, tenant: TenantId, workspace: WorkspaceId | None = None
    ) -> dict[str, SettingRow]:
        """The settings stored on a tenant, with None, or in one of its workspaces, by key."""
        return await self._read(tenant, lambda reads: reads.settings(tenant, workspace))

    async def approval(self, tenant: TenantId, id: ApprovalId) -> Approval | None:
        """One of the tenant's approvals, as it stands; None if it has no such approval."""
        return await self._read(tenant, lambda reads: reads.approval(tenant, id))

    async def approvals(
        self,
        tenant: TenantId,
        *,
        workspace: WorkspaceId | None = None,
        due: datetime | None = None,
    ) -> list[Approval]:
        """The tenant's pending approvals, oldest first: in one workspace, or those due."""
        return await self._read(
            tenant, lambda reads: reads.approvals(tenant, workspace=workspace, due=due)
        )

    async def bindings(
        self,
        tenant: TenantId,
        *,
        workspace: WorkspaceId | None = None,
        source: str | None = None,
        connection: str | None = None,
    ) -> list[Binding]:
        """The tenant's bindings, oldest first: reaching a workspace, or of a connection."""
        return await self._read(
            tenant,
            lambda reads: reads.bindings(
                tenant, workspace=workspace, source=source, connection=connection
            ),
        )

    async def connections(
        self, tenant: TenantId, *, user: UserId | None = None, client: str | None = None
    ) -> list[Connection]:
        """The tenant's connections, oldest first: one person's, or a client's, or every one."""
        return await self._read(
            tenant, lambda reads: reads.connections(tenant, user=user, client=client)
        )

    async def connection(self, tenant: TenantId, id: str) -> Connection | None:
        """One of the tenant's connections, by its id."""
        return await self._read(tenant, lambda reads: reads.connection(tenant, id))

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
            return [_grant(row) for row in await to_the_end(session.scalars(query))]

    async def key(self, key_id: str) -> Key | None:
        """A key, by its public id, in any tenant."""
        async with self._across() as session:
            row = await to_the_end(session.get(KeyRow, key_id))
            return None if row is None else _stored_key(row)

    async def tenants(self) -> list[TenantId]:
        """Every tenant, in order."""
        async with self._across() as session:
            ids = await to_the_end(
                session.scalars(select(TenantRow.id).where(TenantRow.live).order_by(TenantRow.id))
            )
            return list(ids)

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
        ``last``, still oldest first, or every one with neither; the last are read backwards
        from the window's end. A single type, or a single actor, is one index's range; a type
        and an actor together are an index's range and a filter. On PostgreSQL that holds for a
        window's either end; SQLite may scan the tenant's index instead.
        """
        query = audit_query(
            tenant, after_seq=after_seq, before_seq=before_seq, limit=limit, last=last, keep=keep
        )
        async with self._session(tenant) as session:
            rows = list(await to_the_end(session.scalars(query)))
            if last is not None:
                rows.reverse()
            return [
                AuditEntry.model_validate({**row.body, "seq": row.seq, "tenant": tenant})
                for row in rows
            ]


def audit_query(
    tenant: TenantId | None,
    *,
    after_seq: int = 0,
    before_seq: int | None = None,
    limit: int | None = None,
    last: int | None = None,
    keep: AuditFilter | None = None,
) -> Select[AuditRow]:
    """The query :meth:`SqlStorage.audit` reads: the window, the filter, and the first or last.

    The last are ordered backwards from the window's end, for the caller to turn around.
    """
    query = select(AuditRow).where(AuditRow.tenant_id == _scope(tenant), AuditRow.seq > after_seq)
    if before_seq is not None:
        query = query.where(AuditRow.seq < before_seq)
    if keep is not None and keep.types:
        query = query.where(AuditRow.event_type.in_(sorted(keep.types)))
    if keep is not None and keep.by is not None:
        kind, workspace, id = actor_columns(keep.by)
        query = query.where(
            AuditRow.actor_kind == kind,
            AuditRow.actor_workspace == workspace,
            AuditRow.actor_id == id,
        )
    if last is not None:
        return query.order_by(AuditRow.seq.desc()).limit(last)
    return query.order_by(AuditRow.seq).limit(limit)
