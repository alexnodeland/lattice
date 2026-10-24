"""Grants: the checks the libraries' hooks ask, and the commands that change access.

Every command is made by a subject, checked with grantr's own actions, bounded by what that
subject holds, and recorded in the audit log in the same transaction as the change. Checks
deny by default: an unknown action, a principal with no grant that applies, and a store that
can't be read are each a refusal. So is an integration: one the deployment doesn't install, or
whose settings can't be read, is off.
"""

import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable, Collection, Iterable, Mapping
from contextlib import asynccontextmanager
from datetime import timedelta
from types import MappingProxyType
from typing import Final, NamedTuple, Protocol

from opentelemetry.metrics import MeterProvider
from opentelemetry.trace import TracerProvider

from grantr.core import (
    APPLICATION,
    BUILT_IN,
    DEPLOYMENT,
    MEMBER,
    TENANT,
    TENANT_ID,
    Agent,
    AuditEntry,
    AuditEvent,
    AuditFilter,
    Catalog,
    CatalogView,
    DeploymentTenantCreated,
    Forbidden,
    Grant,
    Granted,
    Grantee,
    Group,
    GroupDefined,
    GroupDeleted,
    IntegrationSet,
    IntegrationSetting,
    IntegrationState,
    Invalid,
    Key,
    KeyIssued,
    KeyRevoked,
    ListableKind,
    Member,
    MemberAdded,
    MemberRemoved,
    Membership,
    Resource,
    ResourceKind,
    Restricted,
    Revoked,
    Role,
    RoleDefined,
    RoleDeleted,
    RulePrincipal,
    ServicePrincipal,
    SettingRow,
    SettingSet,
    SettingState,
    SettingsView,
    Stale,
    Subject,
    TenantCreated,
    TenantDeleted,
    TenantId,
    Unrestricted,
    User,
    UserId,
    Visibility,
    WorkspaceId,
    issue,
    key_id,
    memberships,
    verify,
)
from grantr.core.grants import held
from grantr.core.roles import MANAGE_INTEGRATIONS, MANAGE_SETTINGS, RESTRICT, RULE_ROLE
from grantr.core.settings import state as setting_state
from grantr.core.settings import wire
from grantr.grants.storage import Reads, Storage, Transaction
from grantr.telemetry import SLOW_CHECK, Reason, Telemetry
from lattice_core.integrations import KNOWN, Integration
from lattice_core.settings import KNOWN_SETTINGS, Setting, Value, floor, operator_layer

logger = logging.getLogger(__name__)

type MemberRemovedHook = Callable[[TenantId, Member], Awaitable[None]]
"""What another package runs once a member is removed from a tenant: the tenant and the member."""

type Record = Callable[[TenantId | None, Subject | None, AuditEvent], Awaitable[AuditEntry]]
"""Appends an audit entry in a change's transaction."""


class Access(Protocol):
    """What an actor is about to do: a library's ``Access``, read by its fields' names.

    artifactr's has ``thread_id`` and ``artifact_id``, and reflexr's has ``rule``; grantr reads
    whichever it has.
    """

    @property
    def action(self) -> str:
        """The qualified action, such as ``artifactr:edit_artifact``."""
        ...


DEFAULT_PAGE: Final = 100
"""How many audit entries a read returns when it asks for neither a first nor a last count."""

RESTRICTABLE: Final = frozenset({"thread", "artifact"})
"""The kinds of item that can be restricted."""

NAMED: Final[tuple[tuple[ResourceKind, str], ...]] = (
    ("thread", "thread_id"),
    ("artifact", "artifact_id"),
    ("rule", "rule"),
)
"""The items an access may name: each kind, by the field of the libraries' ``Access``."""

type SubjectOf[A] = Callable[[TenantId, WorkspaceId | None, A], Subject]
"""Maps a library's actor, in a tenant and workspace, to the subject grantr checks."""


class Hooks[A](NamedTuple):
    """The libraries' ``authorize`` and ``hidden`` hooks, answered by grantr."""

    authorize: Callable[[TenantId, WorkspaceId | None, A, Access], Awaitable[bool]]
    hidden: Callable[[TenantId, WorkspaceId, A], Awaitable[Visibility]]


def _resources_of(workspace: WorkspaceId | None, access: Access) -> list[Resource]:
    """What an access is about: each item it names, else its workspace, else the tenant.

    An access that names a thread and an artifact is about both, and is allowed only if each is.
    """
    if workspace is None:
        return [TENANT]
    named = [
        Resource(kind=kind, workspace=workspace, id=value)
        for kind, field in NAMED
        if isinstance(value := getattr(access, field, None), str)
    ]
    return named or [Resource(kind="workspace", workspace=workspace)]


class Grants:
    """grantr: who may do what, and the commands that change it.

    Args:
        storage: Where access is kept.
        catalogs: Each library's ``ACTIONS``, and any other catalog the application has, such
            as portalr's. grantr adds its own. An action in none of them is always refused.
        tracer_provider: Where slow checks' spans go. Defaults to the global tracer provider.
        meter_provider: Where the check counter goes. Defaults to the global meter provider.
        slow_check: How long a check takes before it is recorded as a span.
        application: The application's own service principal, which :meth:`bootstrap` grants
            the ``application`` role.
        integrations: The integrations a tenant's admins switch, by key: lattice's,
            :data:`~lattice_core.integrations.KNOWN`, if omitted.
        installed: The keys of those the deployment installs; every one if omitted. One it
            doesn't install is off everywhere, whatever is set.
        settings: The settings a tenant's and a workspace's admins narrow, by key: lattice's,
            :data:`~lattice_core.settings.KNOWN_SETTINGS`, if omitted.
        operator_settings: The operator's values, by key, which replace the settings' defaults
            and are the ceiling every tenant narrows; checked as the deployment starts.

    Raises:
        ValueError: If it installs an integration that ``integrations`` doesn't declare, or the
            operator sets a setting ``settings`` doesn't declare, or a value of the wrong kind.
    """

    def __init__(
        self,
        storage: Storage,
        *,
        catalogs: Iterable[Iterable[str]] = (),
        tracer_provider: TracerProvider | None = None,
        meter_provider: MeterProvider | None = None,
        slow_check: timedelta = SLOW_CHECK,
        application: ServicePrincipal | None = None,
        integrations: Mapping[str, Integration] = KNOWN,
        installed: Collection[str] | None = None,
        settings: Mapping[str, Setting] = KNOWN_SETTINGS,
        operator_settings: Mapping[str, object] = MappingProxyType({}),
    ) -> None:
        if installed is not None and (unknown := sorted(set(installed) - set(integrations))):
            raise ValueError(f"installs integrations it doesn't declare: {', '.join(unknown)}")
        self._storage = storage
        self._integrations = integrations
        self._installed = frozenset(integrations if installed is None else installed)
        self._settings_known = settings
        self._operator = operator_layer(settings, operator_settings)
        self._catalog = Catalog.of(*catalogs)
        self._application = application
        self._telemetry = Telemetry(
            tracer_provider=tracer_provider, meter_provider=meter_provider, slow_check=slow_check
        )
        self._on_member_removed: list[MemberRemovedHook] = []

    def on_member_removed(self, hook: MemberRemovedHook) -> None:
        """Run ``hook`` each time a member is removed from a tenant, once the removal is kept.

        Each hook is awaited in turn after the removal commits, with the tenant and the member.
        One that fails is logged, by its error's type, and changes nothing: the removal stands,
        and the other hooks run. A hook that must not miss a removal keeps its own work owed, as
        portalr's does (grantr ADR-0036). Registering the same hook again changes nothing. A
        removal cancelled while its hooks run, as its request is, skips the hooks still to run.
        """
        if hook not in self._on_member_removed:
            self._on_member_removed.append(hook)

    # ─── checks ──────────────────────────────────────────────────────────────

    async def check(self, tenant: TenantId, subject: Subject, action: str, on: Resource) -> bool:
        """Whether a subject may take an action on a resource in a tenant."""
        start = time.time_ns()
        refused = await self._refusal(tenant, subject, action, on)
        self._telemetry.checked(tenant, action, refused, start=start, end=time.time_ns())
        if refused:
            logger.debug("refused %s on %s: %s", action, on, refused)
        return refused is None

    async def _refusal(
        self, tenant: TenantId, subject: Subject, action: str, on: Resource
    ) -> Reason | None:
        """Why a check is refused, or None if it is allowed."""
        if action not in self._catalog.actions:
            return "unknown_action"
        try:
            held = await self._held(self._storage, tenant, subject, on)
        except Exception:
            logger.warning("refused %s: the store can't be read", action, exc_info=True)
            return "store_unreadable"
        return None if action in held else "no_grant"

    async def hidden(
        self, tenant: TenantId, subject: Subject, workspace: WorkspaceId
    ) -> Visibility:
        """The threads and artifacts a subject may not see in a workspace.

        A restricted thread or artifact is hidden from everyone but those granted a role on it,
        and those who may restrict it: the workspace's admins, and the tenant's owners and
        admins. The application's own principal sees everything.
        """
        items = await self._storage.restricted(tenant, workspace)
        if not items or await self._sees_everything(subject):
            return Visibility()
        hidden = list(items)
        if not isinstance(subject, Agent):
            grants = _implied(tenant, subject, await self._storage.grants(tenant, subject))
            custom = await self._custom(self._storage, tenant, grants)
            hidden = [
                item
                for item in items
                if not held(grants, item, self._catalog, custom, restricted=True)
            ]
        return Visibility(
            threads=frozenset(item.id for item in hidden if item.kind == "thread" and item.id),
            artifacts=frozenset(item.id for item in hidden if item.kind == "artifact" and item.id),
        )

    async def _sees_everything(self, subject: Subject) -> bool:
        """Whether a subject is the application's own principal, holding its role."""
        return (
            isinstance(subject, ServicePrincipal)
            and subject == self._application
            and await self._storage.has(_application(subject))
        )

    async def resources(
        self, tenant: TenantId, subject: Subject, action: str, kind: ListableKind
    ) -> list[Resource]:
        """The resources of a kind on which a subject may take an action.

        Such as the workspaces a user can open. A workspace, thread, artifact or rule is known
        to grantr once a grant names it, or an item in it.
        """
        if action not in self._catalog.actions or isinstance(subject, Agent):
            return []
        candidates = await self._storage.resources(tenant, kind)
        grants = _implied(tenant, subject, await self._storage.grants(tenant, subject))
        custom = await self._custom(self._storage, tenant, grants)
        restricted = (
            frozenset(await self._storage.restricted(tenant)) if kind in RESTRICTABLE else ()
        )
        return [
            r
            for r in candidates
            if action in held(grants, r, self._catalog, custom, restricted=r in restricted)
        ]

    async def member(self, tenant: TenantId, user: UserId) -> Membership | None:
        """A user's membership of a tenant, or None if they aren't a member."""
        roles = await self.tenant_roles(tenant, User(id=user))
        return Membership(tenant=tenant, user=user, roles=roles) if roles else None

    async def tenant_roles(self, tenant: TenantId, member: Member) -> tuple[str, ...]:
        """A user's or service principal's roles on a tenant, sorted; none if not a member."""
        granted = await self._storage.grants(tenant, member, on=[TENANT])
        return tuple(sorted(grant.role for grant in granted if grant.to == member))

    async def workspaces(self, tenant: TenantId, member: Member) -> list[WorkspaceId]:
        """The workspaces a member can open: those where it holds any library's ``open``.

        It reads the member's grants, and the tenant's custom roles if they name one, once.
        """
        grants = await self._storage.grants(tenant, member)
        custom = await self._custom(self._storage, tenant, grants)
        return [
            workspace.workspace
            for workspace in await self._storage.resources(tenant, "workspace")
            if workspace.workspace and _opens(held(grants, workspace, self._catalog, custom))
        ]

    async def memberships(self, user: UserId) -> list[Membership]:
        """Every tenant a user is a member of, with their roles in it."""
        return memberships(user, await self._storage.tenant_grants(user))

    async def authenticate(self, key: str) -> tuple[TenantId, ServicePrincipal] | None:
        """The tenant and service principal a key belongs to, or None if it isn't a valid key."""
        found = key_id(key)
        stored = await self._storage.key(found) if found else None
        if stored is None or stored.principal == self._application or not verify(key, stored):
            return None
        return stored.tenant, stored.principal

    def hooks[A](self, subject_of: SubjectOf[A]) -> Hooks[A]:
        """The libraries' ``authorize`` and ``hidden`` hooks, for their ``Workspaces``.

        Args:
            subject_of: Maps the library's actor to the subject to check, as the template does:
                a user to the user, an agent acting for a user to that user, and so on.
        """

        async def authorize(
            tenant: TenantId, workspace: WorkspaceId | None, actor: A, access: Access
        ) -> bool:
            subject = subject_of(tenant, workspace, actor)
            for resource in _resources_of(workspace, access):
                if not await self.check(tenant, subject, access.action, resource):
                    return False
            return True

        async def hidden(tenant: TenantId, workspace: WorkspaceId, actor: A) -> Visibility:
            return await self.hidden(tenant, subject_of(tenant, workspace, actor), workspace)

        return Hooks(authorize, hidden)

    # ─── what an admin lists ─────────────────────────────────────────────────
    # Each list is read with the action of the command that changes it.

    async def restrictions(
        self, tenant: TenantId, workspace: WorkspaceId, *, by: Subject
    ) -> list[Resource]:
        """The threads and artifacts restricted in a workspace.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:restrict`` on the workspace.
        """
        on = Resource(kind="workspace", workspace=workspace)
        await self._require(self._storage, tenant, by, RESTRICT, on)
        return await self._storage.restricted(tenant, workspace)

    async def served_tenants(self) -> list[TenantId]:
        """Every tenant, for the deployment's own in-process tools, such as a startup task.

        It checks no one: no surface reaches it, as none reaches :meth:`provision_tenant`.
        Surfaces list tenants with :meth:`tenants`, for an operator.
        """
        return await self._storage.tenants()

    async def tenants(self, *, by: Subject) -> list[TenantId]:
        """Every tenant, for an operator.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:create_tenant`` on the deployment.
        """
        await self._require(self._storage, None, by, "grantr:create_tenant", DEPLOYMENT)
        return await self._storage.tenants()

    async def members(self, tenant: TenantId, *, by: Subject) -> list[Member]:
        """A tenant's members.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:add_member`` on the tenant.
        """
        await self._require(self._storage, tenant, by, "grantr:add_member", TENANT)
        granted = await self._storage.granted(tenant, TENANT, role=MEMBER)
        return [grant.to for grant in granted if isinstance(grant.to, User | ServicePrincipal)]

    async def groups(self, tenant: TenantId, *, by: Subject) -> dict[str, frozenset[Member]]:
        """A tenant's groups, by id, with their members.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:manage_groups`` on the tenant.
        """
        await self._require(self._storage, tenant, by, "grantr:manage_groups", TENANT)
        return await self._storage.groups(tenant)

    async def roles(self, tenant: TenantId, *, by: Subject) -> list[Role]:
        """A tenant's custom roles.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:define_role`` on the tenant.
        """
        await self._require(self._storage, tenant, by, "grantr:define_role", TENANT)
        return sorted((await self._storage.roles(tenant)).values(), key=lambda role: role.name)

    async def grants_in(
        self, tenant: TenantId, *, by: Subject, workspace: WorkspaceId | None = None
    ) -> list[Grant]:
        """Every grant in a tenant, or on a workspace and the items in it.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:grant`` on the tenant, or on the workspace.
        """
        on = TENANT if workspace is None else Resource(kind="workspace", workspace=workspace)
        await self._require(self._storage, tenant, by, "grantr:grant", on)
        return await self._storage.grants_in(tenant, workspace=workspace)

    async def keys(self, tenant: TenantId, *, by: Subject) -> list[Key]:
        """A tenant's keys, which hold their secrets' digests and never the secrets.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:issue_key`` on the tenant.
        """
        await self._require(self._storage, tenant, by, "grantr:issue_key", TENANT)
        return await self._storage.keys(tenant)

    async def audit(
        self,
        tenant: TenantId | None,
        *,
        by: Subject,
        after_seq: int = 0,
        before_seq: int | None = None,
        limit: int | None = None,
        last: int | None = None,
        keep: AuditFilter | None = None,
    ) -> list[AuditEntry]:
        """A tenant's audit log in the window ``after_seq < seq < before_seq``, oldest first.

        The deployment's with ``None``. Of the entries ``keep`` keeps (of some types, by one
        actor, or every one): the first ``limit``, 100 with neither, or the last ``last``. A
        client pages back with ``last`` and its oldest entry's ``seq`` as ``before_seq``, as
        artifactr's log does, and catches up with its newest as ``after_seq``: a page shorter
        than it asked for holds all there is.

        Raises:
            Invalid: If it gives both ``limit`` and ``last``.
            Forbidden: If ``by`` may not read it: ``grantr:read_audit`` on the tenant, or
                ``grantr:grant_operator`` for the deployment's.
        """
        if limit is not None and last is not None:
            raise Invalid("give limit or last, not both")
        if tenant is None:
            await self._require(self._storage, None, by, "grantr:grant_operator", DEPLOYMENT)
        else:
            await self._require(self._storage, tenant, by, "grantr:read_audit", TENANT)
        return await self._storage.audit(
            tenant,
            after_seq=after_seq,
            before_seq=before_seq,
            limit=DEFAULT_PAGE if limit is None and last is None else limit,
            last=last,
            keep=keep,
        )

    def catalog(self) -> CatalogView:
        """What a tenant's roles may be: the built-in roles, and what a custom one may hold.

        It is the deployment's, and anyone may read it.
        """
        return self._catalog.view()

    # ─── commands ────────────────────────────────────────────────────────────

    async def first_operator(self, user: UserId) -> AuditEntry:
        """Make a user the deployment's first operator, which no one grants.

        Raises:
            Invalid: If the deployment has an operator already.
        """
        async with self._change(None) as (tx, record):
            if await tx.granted(None, DEPLOYMENT, role="operator"):
                raise Invalid("the deployment has an operator already")
            grant = Grant(tenant=None, role="operator", on=DEPLOYMENT, to=User(id=user))
            await tx.add_grant(grant)
            return await record(None, None, Granted(grant=grant))

    async def bootstrap(self) -> list[AuditEntry]:
        """Make the configured principal the one that holds the ``application`` role.

        The application calls it as it starts; nothing else grants the role. It grants the role
        to the principal ``Grants`` was made with, if it hasn't it, and revokes it from any
        other, as when the application's principal is renamed, each in an audit entry made by
        no one. Replicas starting together grant it once.

        Returns:
            The audit entries; none if nothing changed.

        Raises:
            Invalid: If ``Grants`` was made with no ``application`` principal.
        """
        if self._application is None:
            raise Invalid("no application principal is configured")
        grant = _application(self._application)
        # The deployment's changes run one at a time, so replicas starting together grant once.
        async with self._change(None) as (tx, record):
            entries: list[AuditEntry] = []
            for other in await tx.granted(None, DEPLOYMENT, role=APPLICATION):
                if other != grant:
                    await tx.remove_grant(other)
                    entries.append(await record(None, None, Revoked(grant=other)))
            if not await tx.has(grant):
                await tx.add_grant(grant)
                entries.append(await record(None, None, Granted(grant=grant)))
            return entries

    async def grant_operator(self, user: UserId, *, by: Subject) -> AuditEntry:
        """Make a user an operator of the deployment.

        Raises:
            Forbidden: If ``by`` isn't an operator.
            Invalid: If the user is one already.
        """
        grant = Grant(tenant=None, role="operator", on=DEPLOYMENT, to=User(id=user))
        async with self._change(None) as (tx, record):
            await self._require(tx, None, by, "grantr:grant_operator", DEPLOYMENT)
            if await tx.has(grant):
                raise Invalid(f"{user} is an operator already")
            await tx.add_grant(grant)
            return await record(None, by, Granted(grant=grant))

    async def revoke_operator(self, user: UserId, *, by: Subject) -> AuditEntry:
        """Stop a user being an operator of the deployment.

        Raises:
            Forbidden: If ``by`` isn't an operator.
            Invalid: If the user isn't one.
        """
        grant = Grant(tenant=None, role="operator", on=DEPLOYMENT, to=User(id=user))
        async with self._change(None) as (tx, record):
            await self._require(tx, None, by, "grantr:grant_operator", DEPLOYMENT)
            if not await tx.has(grant):
                raise Invalid(f"{user} isn't an operator")
            await tx.remove_grant(grant)
            return await record(None, by, Revoked(grant=grant))

    async def create_tenant(self, tenant: TenantId, *, owner: UserId, by: Subject) -> AuditEntry:
        """Create a tenant, with a user as its first owner.

        The creation is recorded twice, in the same transaction: ``tenant_created`` in the
        tenant's log, which this returns, and ``deployment_tenant_created`` in the deployment's,
        which names the tenant and its owner, and ``by``, so an operator who isn't a member of
        the tenant is seen to have created it.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:create_tenant`` on the deployment.
            Invalid: If the tenant exists, or its id is empty or has a ``~``.
        """
        _tenant_id(tenant)
        async with self._change(tenant) as (tx, record):
            await self._require(tx, None, by, "grantr:create_tenant", DEPLOYMENT)
            if await tx.tenant(tenant):
                raise Invalid(f"{tenant} exists")
            created = await self._create(tx, record, tenant, owner, by)
            await self._record_creation(record, tenant, owner, by)
            return created

    async def provision_tenant(
        self, tenant: TenantId, *, owner: UserId, admins: Iterable[UserId] = ()
    ) -> list[AuditEntry]:
        """Create a tenant with its owner, and give it the admins it lacks: the deployment's tools.

        A tenant is created only if it is new, and each of ``admins`` who isn't yet a member is
        made a member and an admin. ``make tenant`` and ``make migrate-tenants`` call it in
        process; no surface reaches it, and its audit entries are made by no one. It removes no
        one and changes no member's roles, so it can run again: a tenant that exists keeps its
        owner, and gains the admins it lacks.

        Returns:
            The audit entries, in order: a new tenant's ``tenant_created``, the admins' entries,
            and last the deployment's ``deployment_tenant_created`` for a new tenant; none if
            nothing changed.

        Raises:
            Invalid: If the tenant's id is empty or has a ``~``.
        """
        _tenant_id(tenant)
        async with self._change(tenant) as (tx, record):
            entries: list[AuditEntry] = []
            new = not await tx.tenant(tenant)
            if new:
                entries.append(await self._create(tx, record, tenant, owner, None))
            for admin in dict.fromkeys(admins):
                user = User(id=admin)
                if await self._is_member(tx, tenant, user):
                    continue
                await tx.add_grant(Grant(tenant=tenant, role=MEMBER, on=TENANT, to=user))
                entries.append(await record(tenant, None, MemberAdded(member=user)))
                grant = Grant(tenant=tenant, role="admin", on=TENANT, to=user)
                await tx.add_grant(grant)
                entries.append(await record(tenant, None, Granted(grant=grant)))
            if new:
                # Last, so the deployment log's lock is held for as short a time as it can be.
                entries.append(await self._record_creation(record, tenant, owner, None))
            return entries

    async def delete_tenant(self, tenant: TenantId, *, by: Subject) -> AuditEntry:
        """Delete a tenant, and everything grantr holds for it but its audit log.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:delete_tenant`` on the tenant.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:delete_tenant", TENANT)
            await tx.delete_tenant(tenant)
            return await record(tenant, by, TenantDeleted())

    async def add_member(self, tenant: TenantId, member: Member, *, by: Subject) -> AuditEntry:
        """Add a user or service principal to a tenant, with the ``member`` role.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:add_member`` on the tenant.
            Invalid: If it is a member already, or the application's own principal.
        """
        if member == self._application:
            raise Invalid("the application's principal is no tenant's member")
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:add_member", TENANT)
            if await self._is_member(tx, tenant, member):
                raise Invalid(f"{member} is a member already")
            await tx.add_grant(Grant(tenant=tenant, role=MEMBER, on=TENANT, to=member))
            return await record(tenant, by, MemberAdded(member=member))

    async def remove_member(self, tenant: TenantId, member: Member, *, by: Subject) -> AuditEntry:
        """Remove a member from a tenant, with its grants, its places in groups and its keys.

        Raises:
            Forbidden: If ``by`` may not (``grantr:remove_member`` on the tenant), or holds less
                than a role it would revoke.
            Invalid: If it isn't a member, or is the tenant's last member holding ``owner``.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:remove_member", TENANT)
            if not await self._is_member(tx, tenant, member):
                raise Invalid(f"{member} isn't a member")
            own = [grant for grant in await tx.grants(tenant, member) if grant.to == member]
            await self._bounded(tx, tenant, by, own)
            await self._keeps_an_owner(tx, tenant, leaving=member)
            await tx.remove_member(tenant, member)
            entry = await record(tenant, by, MemberRemoved(member=member))
        for hook in self._on_member_removed:
            try:
                await hook(tenant, member)
            except Exception as error:  # A hook never undoes, or fails, the removal it follows.
                named = getattr(hook, "__qualname__", "hook")
                logger.warning("member-removed hook %s failed: %s", named, type(error).__name__)
        return entry

    async def define_group(
        self, tenant: TenantId, group: Group, members: frozenset[Member], *, by: Subject
    ) -> AuditEntry:
        """Create a group, or replace its members.

        Raises:
            Forbidden: If ``by`` may not (``grantr:manage_groups`` on the tenant), or holds less
                than a role the group is granted, which its members gain or lose.
            Invalid: If one of the members isn't a member of it, or the change would leave the
                tenant with no member holding ``owner``.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:manage_groups", TENANT)
            for member in members:
                if not await self._is_member(tx, tenant, member):
                    raise Invalid(f"{member} isn't a member")
            await self._bounded(tx, tenant, by, await tx.grants(tenant, group))
            await self._keeps_an_owner(tx, tenant, regrouped=(group, members))
            await tx.put_group(tenant, group, members)
            return await record(tenant, by, GroupDefined(group=group.id, members=members))

    async def delete_group(self, tenant: TenantId, group: Group, *, by: Subject) -> AuditEntry:
        """Delete a group, with its grants.

        Raises:
            Forbidden: If ``by`` may not (``grantr:manage_groups`` on the tenant), or holds less
                than a role the group is granted.
            Invalid: If there is no such group, or deleting it would leave the tenant with no
                member holding ``owner``.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:manage_groups", TENANT)
            if await tx.group(tenant, group) is None:
                raise Invalid(f"there is no group {group.id}")
            carried = await tx.grants(tenant, group)
            await self._bounded(tx, tenant, by, carried)
            await self._keeps_an_owner(tx, tenant, losing=carried)
            await tx.remove_group(tenant, group)
            return await record(tenant, by, GroupDeleted(group=group.id))

    async def define_role(self, tenant: TenantId, role: Role, *, by: Subject) -> AuditEntry:
        """Create a custom role, or replace its actions.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:define_role`` on the tenant. Whoever may holds
                every action a custom role can, so defining one gives no more than they hold.
            Invalid: If the role isn't valid against the catalogs.
        """
        self._catalog.check(role)
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:define_role", TENANT)
            await tx.put_role(tenant, role)
            return await record(tenant, by, RoleDefined(role=role))

    async def delete_role(self, tenant: TenantId, name: str, *, by: Subject) -> AuditEntry:
        """Delete a custom role, with its grants.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:define_role`` on the tenant.
            Invalid: If there is no such custom role.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:define_role", TENANT)
            role = (await tx.roles(tenant)).get(name)
            if role is None:
                raise Invalid(f"there is no custom role {name}")
            await tx.remove_role(tenant, name)
            return await record(tenant, by, RoleDeleted(role=name))

    async def grant(
        self, tenant: TenantId, role: str, *, on: Resource, to: Grantee, by: Subject
    ) -> AuditEntry:
        """Grant a role on a resource in a tenant.

        An operator may grant themselves any role in a tenant, which makes them a member of it
        if they aren't one; each step is in the tenant's audit log.

        Raises:
            Forbidden: If ``by`` may not (``grantr:grant`` on the resource), or doesn't hold
                every action the role holds there.
            Invalid: If there is no such group, the role can't be granted there, the grantee
                isn't a member, or the grant exists; or, for an operator, no such tenant.
                ``member`` is given by :meth:`add_member`, and the deployment's roles by
                :meth:`grant_operator` and :meth:`bootstrap`.
        """
        grant = self._grant(tenant, role, on, to)
        async with self._change(tenant) as (tx, record):
            operator = await self._operator_granting_itself(tx, to, by)
            if operator:
                await self._enter(tx, record, tenant, operator)
            else:
                await self._require(tx, tenant, by, "grantr:grant", on)
            await self._grantable(tx, tenant, grant)
            if await tx.has(grant):
                raise Invalid(f"{to} holds {role} there already")
            if not operator:
                await self._bounded(tx, tenant, by, [grant])
            await tx.add_grant(grant)
            return await record(tenant, by, Granted(grant=grant))

    async def revoke(
        self, tenant: TenantId, role: str, *, on: Resource, to: Grantee, by: Subject
    ) -> AuditEntry:
        """Revoke a grant. Anyone may give up a grant of their own.

        Raises:
            Forbidden: If ``by`` may not (``grantr:revoke`` on the resource), or doesn't hold
                every action the role holds there.
            Invalid: If there is no such grant, or it leaves no member holding ``owner``.
                ``member`` is taken by :meth:`remove_member`, and the deployment's roles by
                :meth:`revoke_operator` and :meth:`bootstrap`.
        """
        grant = self._grant(tenant, role, on, to)
        async with self._change(tenant) as (tx, record):
            if to != by:
                await self._require(tx, tenant, by, "grantr:revoke", on)
            if not await tx.has(grant):
                raise Invalid(f"{to} doesn't hold {role} there")
            if to != by:
                await self._bounded(tx, tenant, by, [grant])
            if (grant.role, grant.on) == ("owner", TENANT):
                await self._keeps_an_owner(tx, tenant, losing=[grant])
            await tx.remove_grant(grant)
            return await record(tenant, by, Revoked(grant=grant))

    async def restrict(
        self, tenant: TenantId, on: Resource, *, restricted: bool = True, by: Subject
    ) -> AuditEntry:
        """Restrict a thread or artifact to those granted a role on it, or lift its restriction.

        Its workspace's admins, and the tenant's owners and admins, see it either way.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:restrict`` on the item.
            Invalid: If it isn't a thread or artifact, or is restricted, or not, already.
        """
        if on.kind not in RESTRICTABLE:
            raise Invalid(f"a {on.kind} isn't restricted: only a thread or artifact is")
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, RESTRICT, on)
            if await tx.is_restricted(tenant, on) == restricted:
                raise Invalid(f"the {on.kind} is {'' if restricted else 'not '}restricted already")
            await tx.set_restricted(tenant, on, restricted)
            event = Restricted(on=on) if restricted else Unrestricted(on=on)
            return await record(tenant, by, event)

    async def issue_key(
        self, tenant: TenantId, principal: ServicePrincipal, *, by: Subject
    ) -> tuple[str, AuditEntry]:
        """Issue a key for a service principal: the key, to show once, and its audit entry.

        Raises:
            Forbidden: If ``by`` may not (``grantr:issue_key`` on the tenant), or holds less
                than a role the principal holds, which the key would act with.
            Invalid: If the principal isn't a member.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:issue_key", TENANT)
            if not await self._is_member(tx, tenant, principal):
                raise Invalid(f"{principal} isn't a member")
            await self._bounded(tx, tenant, by, await tx.grants(tenant, principal))
            key, stored = issue(tenant, principal)
            await tx.add_key(stored)
            return key, await record(tenant, by, KeyIssued(principal=principal, key=stored.id))

    async def revoke_key(self, tenant: TenantId, key: str, *, by: Subject) -> AuditEntry:
        """Revoke one of a tenant's keys, by its public id.

        Raises:
            Forbidden: If ``by`` may not (``grantr:revoke_key`` on the tenant), or holds less
                than a role the key's principal holds.
            Invalid: If the tenant has no such key.
        """
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, "grantr:revoke_key", TENANT)
            removed = await tx.remove_key(tenant, key)
            if removed is None:
                raise Invalid(f"{tenant} has no key {key}")
            await self._bounded(tx, tenant, by, await tx.grants(tenant, removed.principal))
            return await record(tenant, by, KeyRevoked(principal=removed.principal, key=key))

    # ─── integrations ────────────────────────────────────────────────────────

    async def is_enabled(self, tenant_id: str, workspace_id: str, key: str, /) -> bool:
        """Whether an integration is on in a tenant's workspace: the application's port.

        It checks no one, as :meth:`hidden` doesn't: the package that asks it is about to act
        for a caller it checks itself. A key the deployment doesn't install, or that it doesn't
        know, is off, and so is every key while the store can't be read. ``Grants`` is
        lattice-core's ``Integrations``, and a bound ``is_enabled`` is relayr's ``Enabled``.
        An id that names no tenant, or an empty one that names no workspace, has everything off.
        """
        if key not in self._installed or not TENANT_ID.fullmatch(tenant_id) or not workspace_id:
            return False
        try:
            on_tenant, in_workspace = await self._settings(self._storage, tenant_id, workspace_id)
        except Exception:
            logger.warning("%s is off: the store can't be read", key, exc_info=True)
            return False
        return self._state(key, on_tenant, in_workspace).enabled

    async def integrations_enabled(
        self, tenant: TenantId, workspace: WorkspaceId, *, by: Subject
    ) -> dict[str, bool]:
        """Whether each integration is on in a workspace, by key: for whoever can open it.

        Raises:
            Invalid: If the workspace's id is empty.
            Forbidden: If ``by`` can't open the workspace: it holds no library's ``open`` there.
        """
        if not _opens(await self._held(self._storage, tenant, by, _level(workspace))):
            raise Forbidden("opening the workspace is refused")
        on_tenant, in_workspace = await self._settings(self._storage, tenant, workspace)
        return {
            key: self._state(key, on_tenant, in_workspace).enabled for key in self._integrations
        }

    async def integrations(
        self, tenant: TenantId, *, workspace: WorkspaceId | None = None, by: Subject
    ) -> list[IntegrationState]:
        """Every integration as it is set on the tenant, or in a workspace, in the registry's order.

        Raises:
            Invalid: If the workspace's id is empty.
            Forbidden: If ``by`` may not: ``grantr:manage_integrations`` on the tenant, or on the
                workspace.
        """
        await self._require(self._storage, tenant, by, MANAGE_INTEGRATIONS, _level(workspace))
        on_tenant, in_workspace = await self._settings(self._storage, tenant, workspace)
        return [self._state(key, on_tenant, in_workspace) for key in self._integrations]

    async def set_integration(
        self,
        tenant: TenantId,
        key: str,
        on: bool | None,
        *,
        workspace: WorkspaceId | None = None,
        by: Subject,
    ) -> IntegrationState:
        """Turn an integration on or off on the tenant or in a workspace, or unset it with None.

        An unset level inherits the one above. Only a change is recorded: setting what is set
        already, or unsetting what isn't, writes and records nothing, and returns the state as it
        is. An integration the deployment doesn't install may be set, and stays off.

        Raises:
            Invalid: If no integration has the key, or the workspace's id is empty.
            Forbidden: If ``by`` may not: ``grantr:manage_integrations`` on the tenant, or on the
                workspace.
        """
        if key not in self._integrations:
            raise Invalid(f"there is no integration {key}")
        level = _level(workspace)
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, MANAGE_INTEGRATIONS, level)
            on_tenant, in_workspace = await self._settings(tx, tenant, workspace)
            stored = (on_tenant if workspace is None else in_workspace).get(key)
            if on == (None if stored is None else stored.on):
                return self._state(key, on_tenant, in_workspace)
            event = IntegrationSet(workspace=workspace, key=key, on=on)
            entry = await record(tenant, by, event)
            setting = None if on is None else IntegrationSetting(on=on, by=by, at=entry.at)
            await tx.set_integration(tenant, workspace, key, setting)
            # A state reads only its own key, so the new setting stands for its level.
            changed = {} if setting is None else {key: setting}
            if workspace is None:
                return self._state(key, changed, in_workspace)
            return self._state(key, on_tenant, changed)

    async def _settings(
        self, reads: Reads, tenant: TenantId, workspace: WorkspaceId | None
    ) -> tuple[dict[str, IntegrationSetting], dict[str, IntegrationSetting]]:
        """The integrations set on the tenant, and in the workspace: none there for None."""
        on_tenant = await reads.integrations(tenant)
        if workspace is None:
            return on_tenant, {}
        return on_tenant, await reads.integrations(tenant, workspace)

    def _state(
        self,
        key: str,
        tenant: Mapping[str, IntegrationSetting],
        workspace: Mapping[str, IntegrationSetting],
    ) -> IntegrationState:
        """An integration's state, from the tenant's settings and a workspace's."""
        integration = self._integrations[key]
        return IntegrationState.of(
            key,
            description=integration.description,
            default=integration.default,
            installed=key in self._installed,
            tenant=tenant.get(key),
            workspace=workspace.get(key),
        )

    # ─── settings ────────────────────────────────────────────────────────────

    async def value(self, tenant_id: str, workspace_id: str, key: str, /) -> Value:
        """A setting's value in a tenant's workspace: lattice-core's ``Settings`` port.

        It checks no one, as :meth:`is_enabled` doesn't. It reads the store each time, with no
        cache: the tenant's layer, then the workspace's, each in a read of its own. While the
        store can't be read, and for a malformed tenant id or an empty workspace id, it answers
        the narrowest value the setting may have, so a failure never widens what a workspace
        may do (lattice ADR-0030). A well-formed id that names no tenant has nothing stored,
        and answers the operator's value, or the default.

        Raises:
            KeyError: For a key no setting declares.
        """
        setting = self._settings_known[key]
        if not TENANT_ID.fullmatch(tenant_id) or not workspace_id:
            return floor(setting)
        try:
            on_tenant = await self._storage.settings(tenant_id)
            in_workspace = await self._storage.settings(tenant_id, workspace_id)
        except Exception:
            logger.warning("%s is at its floor: the store can't be read", key, exc_info=True)
            return floor(setting)
        state = setting_state(
            setting,
            operator=self._operator.get(key),
            tenant=on_tenant.get(key),
            workspace=in_workspace.get(key),
            in_workspace=True,
        )
        return setting.value(state.effective)

    async def settings(
        self, tenant: TenantId, *, workspace: WorkspaceId | None = None, by: Subject
    ) -> SettingsView:
        """Every setting as it is set on the tenant, or in a workspace.

        The stored keys no setting declares any more are listed apart: never applied.

        Raises:
            Invalid: If the workspace's id is empty.
            Forbidden: If ``by`` may not: ``grantr:manage_settings`` on the tenant, or on the
                workspace.
        """
        await self._require(self._storage, tenant, by, MANAGE_SETTINGS, _level(workspace))
        on_tenant, in_workspace = await self._stored(self._storage, tenant, workspace)
        here = on_tenant if workspace is None else in_workspace
        return SettingsView(
            settings=[
                self._setting(key, on_tenant, in_workspace, workspace is not None)
                for key in self._settings_known
            ],
            unknown=sorted(key for key in here if key not in self._settings_known),
        )

    async def set_setting(
        self,
        tenant: TenantId,
        key: str,
        value: object,
        *,
        version: int | None = None,
        workspace: WorkspaceId | None = None,
        by: Subject,
    ) -> SettingState:
        """Narrow a setting on the tenant or in a workspace, or unset it with None.

        A value may only narrow the layer above: no higher a number, no more names. ``version``,
        if given, is the version of this level's setting the caller read: 0 for one never set.
        Setting what is set already changes nothing, and records nothing.

        Raises:
            Invalid: If no setting has the key, the value isn't of its kind, or it would widen
                the layer above, saying which layer and how far it may go.
            Forbidden: If ``by`` may not: ``grantr:manage_settings`` on the tenant, or on the
                workspace; or the level may not set it at all: the operator's alone.
            Stale: If ``version`` isn't the setting's current one there.
        """
        level = _level(workspace)
        async with self._change(tenant) as (tx, record):
            # Who may comes first, as for an integration: a caller who may not learns nothing
            # of which keys exist or what values they take.
            await self._require(tx, tenant, by, MANAGE_SETTINGS, level)
            _named(key, workspace)
            setting = self._settings_known.get(key)
            if setting is None:
                raise Invalid("there is no such setting")
            if not setting.settable_by("tenant" if workspace is None else "workspace"):
                raise Forbidden(f"{key} is set by the {setting.lowest} alone")
            try:
                canonical = None if value is None else setting.value(value)
            except ValueError as error:
                raise Invalid(f"{key} is {error}") from None
            on_tenant, in_workspace = await self._stored(tx, tenant, workspace)
            rows = on_tenant if workspace is None else in_workspace
            stored = rows.get(key)
            current = 0 if stored is None else stored.version
            if version is not None and version != current:
                raise Stale(f"{key} is at version {current} here, not {version}")
            state = self._setting(key, on_tenant, in_workspace, workspace is not None)
            if canonical is not None and not setting.within(
                canonical, setting.value(state.ceiling)
            ):
                raise Invalid(
                    f"{key} may be at most {_said(state.ceiling)} here: the"
                    f" {state.ceiling_set_by}'s value"
                )
            new = None if canonical is None else wire(canonical)
            old = None if stored is None else stored.value
            if new == old:
                return state
            event = SettingSet(workspace=workspace, key=key, old=old, new=new, version=current + 1)
            entry = await record(tenant, by, event)
            row = SettingRow(value=new, version=current + 1, by=by, at=entry.at)
            await tx.set_setting(tenant, workspace, key, row)
            changed = {**rows, key: row}
            if workspace is None:
                return self._setting(key, changed, in_workspace, False)
            return self._setting(key, on_tenant, changed, True)

    async def _stored(
        self, reads: Reads, tenant: TenantId, workspace: WorkspaceId | None
    ) -> tuple[dict[str, SettingRow], dict[str, SettingRow]]:
        """The settings stored on the tenant, and in the workspace: none there for None."""
        on_tenant = await reads.settings(tenant)
        if workspace is None:
            return on_tenant, {}
        return on_tenant, await reads.settings(tenant, workspace)

    def _setting(
        self,
        key: str,
        on_tenant: Mapping[str, SettingRow],
        in_workspace: Mapping[str, SettingRow],
        here_in_workspace: bool,
    ) -> SettingState:
        return setting_state(
            self._settings_known[key],
            operator=self._operator.get(key),
            tenant=on_tenant.get(key),
            workspace=in_workspace.get(key),
            in_workspace=here_in_workspace,
        )

    @asynccontextmanager
    async def _change(self, tenant: TenantId | None) -> AsyncGenerator[tuple[Transaction, Record]]:
        """A transaction, and how to record its audit entries, which are logged once it commits."""
        entries: list[AuditEntry] = []
        async with self._storage.transaction(tenant) as tx:

            async def record(
                tenant: TenantId | None, by: Subject | None, event: AuditEvent
            ) -> AuditEntry:
                entries.append(entry := await tx.append(tenant, by, event))
                return entry

            yield tx, record
        for entry in entries:
            self._telemetry.audited(entry)

    # ─── the rules a command follows ─────────────────────────────────────────

    async def _held(
        self, reads: Reads, tenant: TenantId | None, subject: Subject, on: Resource
    ) -> frozenset[str]:
        """The actions a subject holds on a resource: none for an agent acting for no one."""
        if isinstance(subject, Agent):
            return frozenset()
        scope = None if on.kind == "deployment" else tenant
        grants = _implied(scope, subject, await reads.grants(scope, subject, on=on.chain()))
        # The flag matters only to a grant around the item, so it is read only if there is one.
        restricted = (
            tenant is not None
            and on.kind in RESTRICTABLE
            and any(grant.on != on for grant in grants)
            and await reads.is_restricted(tenant, on)
        )
        custom = await self._custom(reads, scope, grants)
        actions = held(grants, on, self._catalog, custom, restricted=restricted)
        # ``application`` is the one deployment role that holds in every tenant.
        if (
            isinstance(subject, ServicePrincipal)
            and subject == self._application
            and scope is not None
            and await reads.has(_application(subject))
        ):
            actions |= self._catalog.built_in["deployment", APPLICATION]
        return actions

    async def _custom(
        self, reads: Reads, tenant: TenantId | None, grants: list[Grant]
    ) -> dict[str, Role]:
        """The tenant's custom roles, read only if a grant names a role that isn't built in."""
        if tenant is None or all(g.role in BUILT_IN for g in grants):
            return {}
        return await reads.roles(tenant)

    async def _require(
        self, reads: Reads, tenant: TenantId | None, by: Subject, action: str, on: Resource
    ) -> None:
        if action not in await self._held(reads, tenant, by, on):
            raise Forbidden(f"{action} on the {on.kind} is refused")

    async def _bounded(
        self, tx: Transaction, tenant: TenantId, by: Subject, grants: Iterable[Grant]
    ) -> None:
        """No one grants or revokes more than they hold: each grant's actions, where it is."""
        custom = await tx.roles(tenant)
        for grant in grants:
            actions = self._catalog.role(grant.role, grant.on.kind, custom) or frozenset()
            if missing := sorted(actions - await self._held(tx, tenant, by, grant.on)):
                raise Forbidden(f"holds less than {grant.role} gives: {', '.join(missing)}")

    def _grant(self, tenant: TenantId, role: str, on: Resource, to: Grantee) -> Grant:
        """The grant :meth:`grant` and :meth:`revoke` name, if they may name it."""
        if on.kind == "deployment" or role == APPLICATION:
            raise Invalid("the deployment's roles are given by grant_operator and bootstrap")
        if role == MEMBER:
            raise Invalid("member is given by add_member, and taken by remove_member")
        return Grant(tenant=tenant, role=role, on=on, to=to)

    async def _grantable(self, tx: Transaction, tenant: TenantId, grant: Grant) -> None:
        """Check that a new grant's role and grantee exist.

        Its tenant does: a subject that holds ``grantr:grant`` in it holds a grant in it.
        """
        actions = self._catalog.role(grant.role, grant.on.kind, await tx.roles(tenant))
        if actions is None:
            raise Invalid(f"{grant.role} can't be granted on a {grant.on.kind}")
        if grant.role == RULE_ROLE and not isinstance(grant.to, RulePrincipal):
            raise Invalid("rule is a stored rule's own role: no one else holds it")
        if isinstance(grant.to, RulePrincipal):
            if grant.on.workspace != grant.to.workspace:
                raise Invalid(f"{grant.to} acts in its own workspace only")
            if any(action.startswith("grantr:") for action in actions):
                raise Invalid(f"a rule manages no access, so it can't hold {grant.role}")
        if isinstance(grant.to, Group):
            if await tx.group(tenant, grant.to) is None:
                raise Invalid(f"there is no group {grant.to.id}")
        elif isinstance(grant.to, User | ServicePrincipal) and not await self._is_member(
            tx, tenant, grant.to
        ):
            raise Invalid(f"{grant.to} isn't a member")

    async def _create(
        self,
        tx: Transaction,
        record: Record,
        tenant: TenantId,
        owner: UserId,
        by: Subject | None,
    ) -> AuditEntry:
        """Create a tenant whose first owner is a member and its owner, as its entry says."""
        await tx.create_tenant(tenant)
        for role in (MEMBER, "owner"):
            await tx.add_grant(Grant(tenant=tenant, role=role, on=TENANT, to=User(id=owner)))
        return await record(tenant, by, TenantCreated(owner=owner))

    async def _record_creation(
        self, record: Record, tenant: TenantId, owner: UserId, by: Subject | None
    ) -> AuditEntry:
        """Record a tenant's creation in the deployment's log, in the creating transaction.

        Called last, after the tenant's own entry and anything else the transaction does, since
        the deployment log's lock is held from here to the commit.
        """
        return await record(None, by, DeploymentTenantCreated(tenant=tenant, owner=owner))

    async def _is_member(self, reads: Reads, tenant: TenantId, member: Member) -> bool:
        return await reads.has(Grant(tenant=tenant, role=MEMBER, on=TENANT, to=member))

    async def _operator_granting_itself(
        self, reads: Reads, to: Grantee, by: Subject
    ) -> User | None:
        """``by``, if it is an operator granting itself a role: it may enter any tenant."""
        if not (isinstance(by, User) and to == by):
            return None
        return (
            by if "grantr:grant_operator" in await self._held(reads, None, by, DEPLOYMENT) else None
        )

    async def _enter(
        self, tx: Transaction, record: Record, tenant: TenantId, operator: User
    ) -> None:
        """Make an operator a member of a tenant they grant themselves a role in."""
        if not await tx.tenant(tenant):
            raise Invalid(f"there is no tenant {tenant}")
        if not await self._is_member(tx, tenant, operator):
            await tx.add_grant(Grant(tenant=tenant, role=MEMBER, on=TENANT, to=operator))
            await record(tenant, operator, MemberAdded(member=operator))

    async def _keeps_an_owner(
        self,
        tx: Transaction,
        tenant: TenantId,
        *,
        losing: Iterable[Grant] = (),
        leaving: Member | None = None,
        regrouped: tuple[Group, frozenset[Member]] | None = None,
    ) -> None:
        """Refuse a change that would leave no member holding ``owner`` on the tenant, if one does.

        An owner grant to a group makes its members owners, so one to an empty group makes no
        one an owner (ADR-0014's amendment). The change takes the grants ``losing``, removes the
        member ``leaving``, or gives a group new members, ``regrouped``.
        """
        lost = set(losing)
        before: set[Grantee] = set()
        after: set[Grantee] = set()
        for grant in await tx.granted(tenant, TENANT, role="owner"):
            held: frozenset[Grantee] = frozenset((grant.to,))
            kept = held
            if isinstance(grant.to, Group):
                held = await tx.group(tenant, grant.to) or frozenset()
                kept = regrouped[1] if regrouped and regrouped[0] == grant.to else held
            before |= held
            if grant not in lost:
                after |= kept if leaving is None else kept - frozenset((leaving,))
        if before and not after:
            owners = ", ".join(sorted(map(str, before)))
            last = "is the last owner" if len(before) == 1 else "are the last owners"
            raise Invalid(f"{owners} {last}")


def _application(principal: ServicePrincipal) -> Grant:
    """The grant of the ``application`` role to a service principal."""
    return Grant(tenant=None, role=APPLICATION, on=DEPLOYMENT, to=principal)


def _opens(actions: Iterable[str]) -> bool:
    """Whether actions open a workspace: any library's ``open`` does."""
    return any(action.endswith(":open") for action in actions)


def _level(workspace: WorkspaceId | None) -> Resource:
    """Where an integration is set: the tenant, with None, or a workspace."""
    if workspace == "":
        raise Invalid("a workspace's id isn't empty")
    return TENANT if workspace is None else Resource(kind="workspace", workspace=workspace)


LONGEST_NAME: Final = 256
"""The longest workspace id or setting key a setting is stored under."""


def _named(key: str, workspace: WorkspaceId | None) -> None:
    """Refuse a key or a workspace's id too long to store a setting under."""
    if len(key) > LONGEST_NAME or (workspace is not None and len(workspace) > LONGEST_NAME):
        raise Invalid(f"a setting's key and its workspace's id are at most {LONGEST_NAME} long")


def _said(value: int | list[str]) -> str:
    """A value as a refusal says it: a number, or names joined."""
    return ", ".join(value) if isinstance(value, list) else str(value)


def _tenant_id(tenant: TenantId) -> None:
    if not TENANT_ID.fullmatch(tenant):
        raise Invalid("a tenant's id isn't empty, and has no ~")


def _implied(tenant: TenantId | None, subject: Subject, grants: list[Grant]) -> list[Grant]:
    """A subject's grants, with the one it holds without a grant: a stored rule's ``rule`` role.

    A stored rule's principal holds ``rule`` in its own workspace and nowhere else, and a grant
    to it anywhere else, which no grant now makes, counts for nothing (ADR-0029).
    """
    if tenant is None or not isinstance(subject, RulePrincipal):
        return grants
    own = Resource(kind="workspace", workspace=subject.workspace)
    within = [grant for grant in grants if grant.on.workspace == subject.workspace]
    return [*within, Grant(tenant=tenant, role=RULE_ROLE, on=own, to=subject)]
