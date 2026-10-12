"""Grants: the checks the libraries' hooks ask, and the commands that change access.

Every command is made by a subject, checked with grantr's own actions, bounded by what that
subject holds, and recorded in the audit log in the same transaction as the change. Checks
deny by default: an unknown action, a principal with no grant that applies, and a store that
can't be read are each a refusal.
"""

import logging
from collections.abc import Awaitable, Callable, Iterable
from typing import Final, NamedTuple, Protocol

from grantr.core import (
    BUILT_IN,
    DEPLOYMENT,
    MEMBER,
    TENANT,
    Agent,
    AuditEntry,
    Catalog,
    Forbidden,
    Grant,
    Granted,
    Grantee,
    Group,
    GroupDefined,
    GroupDeleted,
    Invalid,
    KeyIssued,
    KeyRevoked,
    ListableKind,
    Member,
    MemberAdded,
    MemberRemoved,
    Membership,
    Resource,
    ResourceKind,
    Revoked,
    Role,
    RoleDefined,
    RoleDeleted,
    ServicePrincipal,
    Subject,
    TenantCreated,
    TenantDeleted,
    TenantId,
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
from grantr.grants.storage import Reads, Storage, Transaction

logger = logging.getLogger(__name__)


class Access(Protocol):
    """What an actor is about to do: a library's ``Access``, read by its fields' names.

    artifactr's has ``thread_id`` and ``artifact_id``, and reflexr's has ``rule``; grantr reads
    whichever it has.
    """

    @property
    def action(self) -> str:
        """The qualified action, such as ``artifactr:edit_artifact``."""
        ...


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
    """

    def __init__(self, storage: Storage, *, catalogs: Iterable[Iterable[str]] = ()) -> None:
        self._storage = storage
        self._catalog = Catalog.of(*catalogs)

    # ─── checks ──────────────────────────────────────────────────────────────

    async def check(self, tenant: TenantId, subject: Subject, action: str, on: Resource) -> bool:
        """Whether a subject may take an action on a resource in a tenant."""
        if action not in self._catalog.actions:
            logger.debug("refused %s: not in any catalog", action)
            return False
        try:
            allowed = action in await self._held(self._storage, tenant, subject, on)
        except Exception:
            logger.warning("refused %s: the store can't be read", action, exc_info=True)
            return False
        if not allowed:
            logger.debug("refused %s on %s: no grant holds it", action, on)
        return allowed

    async def hidden(
        self, tenant: TenantId, subject: Subject, workspace: WorkspaceId
    ) -> Visibility:
        """The threads and artifacts a subject may not see in a workspace.

        No item is restricted until the restricted flag arrives (grantr RFC-0001's phase 5), so
        nothing is hidden.
        """
        del tenant, subject, workspace
        return Visibility()

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
        grants = await self._storage.grants(tenant, subject)
        custom = await self._custom(self._storage, tenant, grants)
        return [r for r in candidates if action in held(grants, r, self._catalog, custom)]

    async def member(self, tenant: TenantId, user: UserId) -> Membership | None:
        """A user's membership of a tenant, or None if they aren't a member."""
        found = memberships(user, await self._storage.grants(tenant, User(id=user), on=[TENANT]))
        return found[0] if found else None

    async def memberships(self, user: UserId) -> list[Membership]:
        """Every tenant a user is a member of, with their roles in it."""
        return memberships(user, await self._storage.tenant_grants(user))

    async def authenticate(self, key: str) -> tuple[TenantId, ServicePrincipal] | None:
        """The tenant and service principal a key belongs to, or None if it isn't a valid key."""
        found = key_id(key)
        stored = await self._storage.key(found) if found else None
        return (stored.tenant, stored.principal) if stored and verify(key, stored) else None

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

    async def audit(
        self, tenant: TenantId | None, *, by: Subject, after_seq: int = 0, limit: int = 100
    ) -> list[AuditEntry]:
        """A tenant's audit log after ``after_seq``, or the deployment's with ``None``.

        Raises:
            Forbidden: If ``by`` may not read it: ``grantr:read_audit`` on the tenant, or
                ``grantr:grant_operator`` for the deployment's.
        """
        if tenant is None:
            await self._require(self._storage, None, by, "grantr:grant_operator", DEPLOYMENT)
        else:
            await self._require(self._storage, tenant, by, "grantr:read_audit", TENANT)
        return await self._storage.audit(tenant, after_seq=after_seq, limit=limit)

    # ─── commands ────────────────────────────────────────────────────────────

    async def first_operator(self, user: UserId) -> AuditEntry:
        """Make a user the deployment's first operator, which no one grants.

        Raises:
            Invalid: If the deployment has an operator already.
        """
        async with self._storage.transaction(None) as tx:
            if await tx.granted(None, DEPLOYMENT, role="operator"):
                raise Invalid("the deployment has an operator already")
            grant = Grant(tenant=None, role="operator", on=DEPLOYMENT, to=User(id=user))
            await tx.add_grant(grant)
            return await tx.append(None, None, Granted(grant=grant))

    async def grant_operator(self, user: UserId, *, by: Subject) -> AuditEntry:
        """Make a user an operator of the deployment.

        Raises:
            Forbidden: If ``by`` isn't an operator.
            Invalid: If the user is one already.
        """
        grant = Grant(tenant=None, role="operator", on=DEPLOYMENT, to=User(id=user))
        async with self._storage.transaction(None) as tx:
            await self._require(tx, None, by, "grantr:grant_operator", DEPLOYMENT)
            if await tx.has(grant):
                raise Invalid(f"{user} is an operator already")
            await tx.add_grant(grant)
            return await tx.append(None, by, Granted(grant=grant))

    async def revoke_operator(self, user: UserId, *, by: Subject) -> AuditEntry:
        """Stop a user being an operator of the deployment.

        Raises:
            Forbidden: If ``by`` isn't an operator.
            Invalid: If the user isn't one.
        """
        grant = Grant(tenant=None, role="operator", on=DEPLOYMENT, to=User(id=user))
        async with self._storage.transaction(None) as tx:
            await self._require(tx, None, by, "grantr:grant_operator", DEPLOYMENT)
            if not await tx.has(grant):
                raise Invalid(f"{user} isn't an operator")
            await tx.remove_grant(grant)
            return await tx.append(None, by, Revoked(grant=grant))

    async def create_tenant(self, tenant: TenantId, *, owner: UserId, by: Subject) -> AuditEntry:
        """Create a tenant, with a user as its first owner.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:create_tenant`` on the deployment.
            Invalid: If the tenant exists.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, None, by, "grantr:create_tenant", DEPLOYMENT)
            if await tx.tenant(tenant):
                raise Invalid(f"{tenant} exists")
            await tx.create_tenant(tenant)
            for role in (MEMBER, "owner"):
                await tx.add_grant(Grant(tenant=tenant, role=role, on=TENANT, to=User(id=owner)))
            return await tx.append(tenant, by, TenantCreated(owner=owner))

    async def delete_tenant(self, tenant: TenantId, *, by: Subject) -> AuditEntry:
        """Delete a tenant, and everything grantr holds for it but its audit log.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:delete_tenant`` on the tenant.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:delete_tenant", TENANT)
            await tx.delete_tenant(tenant)
            return await tx.append(tenant, by, TenantDeleted())

    async def add_member(self, tenant: TenantId, member: Member, *, by: Subject) -> AuditEntry:
        """Add a user or service principal to a tenant, with the ``member`` role.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:add_member`` on the tenant.
            Invalid: If it is a member already.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:add_member", TENANT)
            if await self._is_member(tx, tenant, member):
                raise Invalid(f"{member} is a member already")
            await tx.add_grant(Grant(tenant=tenant, role=MEMBER, on=TENANT, to=member))
            return await tx.append(tenant, by, MemberAdded(member=member))

    async def remove_member(self, tenant: TenantId, member: Member, *, by: Subject) -> AuditEntry:
        """Remove a member from a tenant, with its grants, its places in groups and its keys.

        Raises:
            Forbidden: If ``by`` may not (``grantr:remove_member`` on the tenant), or holds less
                than a role it would revoke.
            Invalid: If it isn't a member, or is the tenant's last owner.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:remove_member", TENANT)
            if not await self._is_member(tx, tenant, member):
                raise Invalid(f"{member} isn't a member")
            own = [grant for grant in await tx.grants(tenant, member) if grant.to == member]
            await self._bounded(tx, tenant, by, own)
            await self._keeps_an_owner(tx, tenant, own)
            await tx.remove_member(tenant, member)
            return await tx.append(tenant, by, MemberRemoved(member=member))

    async def define_group(
        self, tenant: TenantId, group: Group, members: frozenset[Member], *, by: Subject
    ) -> AuditEntry:
        """Create a group, or replace its members.

        Raises:
            Forbidden: If ``by`` may not (``grantr:manage_groups`` on the tenant), or holds less
                than a role the group is granted, which its members gain or lose.
            Invalid: If one of the members isn't a member of it.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:manage_groups", TENANT)
            for member in members:
                if not await self._is_member(tx, tenant, member):
                    raise Invalid(f"{member} isn't a member")
            await self._bounded(tx, tenant, by, await tx.grants(tenant, group))
            await tx.put_group(tenant, group, members)
            return await tx.append(tenant, by, GroupDefined(group=group.id, members=members))

    async def delete_group(self, tenant: TenantId, group: Group, *, by: Subject) -> AuditEntry:
        """Delete a group, with its grants.

        Raises:
            Forbidden: If ``by`` may not (``grantr:manage_groups`` on the tenant), or holds less
                than a role the group is granted.
            Invalid: If there is no such group, or it holds the tenant's last owner grant.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:manage_groups", TENANT)
            if await tx.group(tenant, group) is None:
                raise Invalid(f"there is no group {group.id}")
            carried = await tx.grants(tenant, group)
            await self._bounded(tx, tenant, by, carried)
            await self._keeps_an_owner(tx, tenant, carried)
            await tx.remove_group(tenant, group)
            return await tx.append(tenant, by, GroupDeleted(group=group.id))

    async def define_role(self, tenant: TenantId, role: Role, *, by: Subject) -> AuditEntry:
        """Create a custom role, or replace its actions.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:define_role`` on the tenant. Whoever may holds
                every action a custom role can, so defining one gives no more than they hold.
            Invalid: If the role isn't valid against the catalogs.
        """
        self._catalog.check(role)
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:define_role", TENANT)
            await tx.put_role(tenant, role)
            return await tx.append(tenant, by, RoleDefined(role=role))

    async def delete_role(self, tenant: TenantId, name: str, *, by: Subject) -> AuditEntry:
        """Delete a custom role, with its grants.

        Raises:
            Forbidden: If ``by`` may not: ``grantr:define_role`` on the tenant.
            Invalid: If there is no such custom role.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:define_role", TENANT)
            role = (await tx.roles(tenant)).get(name)
            if role is None:
                raise Invalid(f"there is no custom role {name}")
            await tx.remove_role(tenant, name)
            return await tx.append(tenant, by, RoleDeleted(role=name))

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
                ``member`` is given by :meth:`add_member`, and the deployment's role by
                :meth:`grant_operator`.
        """
        grant = self._grant(tenant, role, on, to)
        async with self._storage.transaction(tenant) as tx:
            operator = await self._operator_granting_itself(tx, to, by)
            if operator:
                await self._enter(tx, tenant, operator)
            else:
                await self._require(tx, tenant, by, "grantr:grant", on)
            await self._grantable(tx, tenant, grant)
            if await tx.has(grant):
                raise Invalid(f"{to} holds {role} there already")
            if not operator:
                await self._bounded(tx, tenant, by, [grant])
            await tx.add_grant(grant)
            return await tx.append(tenant, by, Granted(grant=grant))

    async def revoke(
        self, tenant: TenantId, role: str, *, on: Resource, to: Grantee, by: Subject
    ) -> AuditEntry:
        """Revoke a grant. Anyone may give up a grant of their own.

        Raises:
            Forbidden: If ``by`` may not (``grantr:revoke`` on the resource), or doesn't hold
                every action the role holds there.
            Invalid: If there is no such grant, or it is the tenant's last owner. ``member`` is
                taken by :meth:`remove_member`, and the deployment's role by
                :meth:`revoke_operator`.
        """
        grant = self._grant(tenant, role, on, to)
        async with self._storage.transaction(tenant) as tx:
            if to != by:
                await self._require(tx, tenant, by, "grantr:revoke", on)
            if not await tx.has(grant):
                raise Invalid(f"{to} doesn't hold {role} there")
            if to != by:
                await self._bounded(tx, tenant, by, [grant])
            await self._keeps_an_owner(tx, tenant, [grant])
            await tx.remove_grant(grant)
            return await tx.append(tenant, by, Revoked(grant=grant))

    async def issue_key(
        self, tenant: TenantId, principal: ServicePrincipal, *, by: Subject
    ) -> tuple[str, AuditEntry]:
        """Issue a key for a service principal: the key, to show once, and its audit entry.

        Raises:
            Forbidden: If ``by`` may not (``grantr:issue_key`` on the tenant), or holds less
                than a role the principal holds, which the key would act with.
            Invalid: If the principal isn't a member.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:issue_key", TENANT)
            if not await self._is_member(tx, tenant, principal):
                raise Invalid(f"{principal} isn't a member")
            await self._bounded(tx, tenant, by, await tx.grants(tenant, principal))
            key, stored = issue(tenant, principal)
            await tx.add_key(stored)
            return key, await tx.append(tenant, by, KeyIssued(principal=principal, key=stored.id))

    async def revoke_key(self, tenant: TenantId, key: str, *, by: Subject) -> AuditEntry:
        """Revoke one of a tenant's keys, by its public id.

        Raises:
            Forbidden: If ``by`` may not (``grantr:revoke_key`` on the tenant), or holds less
                than a role the key's principal holds.
            Invalid: If the tenant has no such key.
        """
        async with self._storage.transaction(tenant) as tx:
            await self._require(tx, tenant, by, "grantr:revoke_key", TENANT)
            removed = await tx.remove_key(tenant, key)
            if removed is None:
                raise Invalid(f"{tenant} has no key {key}")
            await self._bounded(tx, tenant, by, await tx.grants(tenant, removed.principal))
            return await tx.append(tenant, by, KeyRevoked(principal=removed.principal, key=key))

    # ─── the rules a command follows ─────────────────────────────────────────

    async def _held(
        self, reads: Reads, tenant: TenantId | None, subject: Subject, on: Resource
    ) -> frozenset[str]:
        """The actions a subject holds on a resource: none for an agent acting for no one."""
        if isinstance(subject, Agent):
            return frozenset()
        scope = None if on.kind == "deployment" else tenant
        grants = await reads.grants(scope, subject, on=on.chain())
        return held(grants, on, self._catalog, await self._custom(reads, scope, grants))

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
        if on.kind == "deployment":
            raise Invalid("the deployment's role is given by grant_operator")
        if role == MEMBER:
            raise Invalid("member is given by add_member, and taken by remove_member")
        return Grant(tenant=tenant, role=role, on=on, to=to)

    async def _grantable(self, tx: Transaction, tenant: TenantId, grant: Grant) -> None:
        """Check that a new grant's role and grantee exist.

        Its tenant does: a subject that holds ``grantr:grant`` in it holds a grant in it.
        """
        if self._catalog.role(grant.role, grant.on.kind, await tx.roles(tenant)) is None:
            raise Invalid(f"{grant.role} can't be granted on a {grant.on.kind}")
        if isinstance(grant.to, Group):
            if await tx.group(tenant, grant.to) is None:
                raise Invalid(f"there is no group {grant.to.id}")
        elif isinstance(grant.to, User | ServicePrincipal) and not await self._is_member(
            tx, tenant, grant.to
        ):
            raise Invalid(f"{grant.to} isn't a member")

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

    async def _enter(self, tx: Transaction, tenant: TenantId, operator: User) -> None:
        """Make an operator a member of a tenant they grant themselves a role in."""
        if not await tx.tenant(tenant):
            raise Invalid(f"there is no tenant {tenant}")
        if not await self._is_member(tx, tenant, operator):
            await tx.add_grant(Grant(tenant=tenant, role=MEMBER, on=TENANT, to=operator))
            await tx.append(tenant, operator, MemberAdded(member=operator))

    async def _keeps_an_owner(
        self, tx: Transaction, tenant: TenantId, losing: Iterable[Grant]
    ) -> None:
        """Refuse a change that would leave the tenant with no owner."""
        owners = await tx.granted(tenant, TENANT, role="owner")
        if owners and set(owners) <= set(losing):
            raise Invalid(f"{owners[0].to} is the last owner")
