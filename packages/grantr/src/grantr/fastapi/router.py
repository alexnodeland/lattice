"""The admin API, and the two reads UIs ask.

Tenants, members, groups, roles, grants, keys and the audit log; and ``/me`` and ``/checks``.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Final, Literal, NamedTuple

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from starlette.requests import HTTPConnection

from grantr.core import (
    AuditEntry,
    Forbidden,
    Grant,
    Grantee,
    GrantrError,
    Group,
    Invalid,
    Member,
    Membership,
    Resource,
    Role,
    ServicePrincipal,
    Subject,
    TenantId,
    User,
    UserId,
    WorkspaceId,
)
from grantr.grants import Grants


class Caller(NamedTuple):
    """Who is calling, as ``resolve_actor`` authenticates them."""

    subject: Subject
    tenant: TenantId | None = None
    """The one tenant the caller may act in, for a service principal's key; None for a user,
    who names the tenant on each request."""


ResolveActor = Callable[[HTTPConnection], Awaitable[Caller]]
"""Authenticates a request: returns its caller, or raises :class:`Unauthorized`."""


class Unauthorized(Exception):
    """Raise from ``resolve_actor`` to refuse a request (401)."""


STATUS_CODES: dict[str, int] = {
    "unauthorized": 401,
    "tenant_required": 400,
    "forbidden": 403,
    "invalid": 422,
}
"""The HTTP status for each refusal ``type``."""


class Me(BaseModel):
    """The caller in one tenant: their roles on it, and the workspaces they can open."""

    model_config = ConfigDict(frozen=True)

    tenant: TenantId
    roles: tuple[str, ...]
    workspaces: list[WorkspaceId]


class Memberships(BaseModel):
    """Every tenant the caller is a member of, when they name none."""

    model_config = ConfigDict(frozen=True)

    memberships: list[Membership]


class Check(BaseModel):
    """One question for ``/checks``: may the caller take this action on this resource?"""

    model_config = ConfigDict(frozen=True)

    action: str
    resource: Resource


class NewTenant(BaseModel):
    """A tenant to create, with its first owner."""

    tenant: TenantId
    owner: UserId


class NewMember(BaseModel):
    """A user or service principal to add to a tenant."""

    member: Member


class GroupMembers(BaseModel):
    """A group's members."""

    members: list[Member]


class RoleActions(BaseModel):
    """A custom role's actions."""

    actions: list[str]


class GrantRequest(BaseModel):
    """A role, on a resource, to a grantee: to grant, or to revoke."""

    role: str
    on: Resource
    to: Grantee


class Restriction(BaseModel):
    """A thread or artifact, and whether it is restricted to those granted a role on it."""

    on: Resource
    restricted: bool = True


class NewKey(BaseModel):
    """The service principal a key is issued to."""

    principal: str


class IssuedKey(BaseModel):
    """A key, shown once, and the audit entry that records it."""

    key: str
    entry: AuditEntry


class KeyView(BaseModel):
    """A key as listed: its public id and its principal."""

    id: str
    principal: ServicePrincipal


MAX_CHECKS: Final = 100
"""The most questions one request to ``/checks`` may ask."""

AfterSeq = Annotated[int, Query(ge=0)]
"""Read the audit entries after this sequence number."""

Limit = Annotated[int, Query(ge=1, le=1000)]
"""Read at most this many audit entries."""

TenantHeader = Annotated[TenantId | None, Header(alias="X-Tenant")]
"""The tenant a request to ``/me`` or ``/checks`` names."""


def grantr_router(grants: Grants, *, resolve_actor: ResolveActor) -> APIRouter:
    """Build the admin API, for an application to mount at ``/grantr/v1``.

    Every command is made by the caller and checked by grantr, with its own actions. A caller
    whose key binds it to one tenant is refused every other.

    Args:
        grants: What the API reads and changes.
        resolve_actor: Authenticates each request.
    """
    router = APIRouter()

    async def caller(request: Request) -> Caller:
        try:
            return await resolve_actor(request)
        except Unauthorized as error:
            raise _refusal("unauthorized", str(error) or "no caller") from error

    current = Depends(caller)

    def by(tenant: TenantId, who: Caller) -> Subject:
        """The caller's subject, if it may act in this tenant at all."""
        if who.tenant is not None and who.tenant != tenant:
            raise _refused(Forbidden("this caller's key is for another tenant"))
        return who.subject

    async def active(who: Caller, named: TenantId | None) -> tuple[TenantId, Member]:
        """The tenant a request names, or the caller's only one, and the caller, a member."""
        tenant = named or who.tenant
        if tenant is None and isinstance(who.subject, User):
            found = await grants.memberships(who.subject.id)
            tenant = found[0].tenant if len(found) == 1 else None
        if tenant is None:
            raise _refusal("tenant_required", "name the tenant with X-Tenant")
        subject = by(tenant, who)
        if isinstance(subject, User | ServicePrincipal) and await grants.tenant_roles(
            tenant, subject
        ):
            return tenant, subject
        raise _refused(Forbidden(f"the caller isn't a member of {tenant}"))

    @router.get("/me")
    async def me(x_tenant: TenantHeader = None, who: Caller = current) -> Me | Memberships:
        """The caller in the tenant ``X-Tenant`` names, or every tenant they are a member of.

        In a tenant: the caller's roles on it, and the workspaces they can open.
        """
        if x_tenant is None and who.tenant is None:
            user = who.subject.id if isinstance(who.subject, User) else None
            return Memberships(memberships=await grants.memberships(user) if user else [])
        tenant, member = await active(who, x_tenant)
        return Me(
            tenant=tenant,
            roles=await grants.tenant_roles(tenant, member),
            workspaces=await grants.workspaces(tenant, member),
        )

    @router.post("/checks")
    async def checks(
        questions: Annotated[list[Check], Body(max_length=MAX_CHECKS)],
        x_tenant: TenantHeader = None,
        who: Caller = current,
    ) -> list[bool]:
        """Answer a batch of up to 100 checks for the caller, in order.

        Each command is checked again when it arrives.
        """
        tenant, member = await active(who, x_tenant)
        return [
            await grants.check(tenant, member, question.action, question.resource)
            for question in questions
        ]

    @router.get("/tenants")
    async def list_tenants(who: Caller = current) -> list[TenantId]:
        """Every tenant, for an operator."""
        return await _or_http(grants.tenants(by=who.subject))

    @router.post("/tenants", status_code=201)
    async def create_tenant(body: NewTenant, who: Caller = current) -> AuditEntry:
        """Create a tenant, with its first owner."""
        return await _or_http(grants.create_tenant(body.tenant, owner=body.owner, by=who.subject))

    @router.delete("/tenants/{tenant}")
    async def delete_tenant(tenant: TenantId, who: Caller = current) -> AuditEntry:
        """Delete a tenant, and everything grantr holds for it but its audit log."""
        return await _or_http(grants.delete_tenant(tenant, by=by(tenant, who)))

    @router.put("/operators/{user}")
    async def grant_operator(user: UserId, who: Caller = current) -> AuditEntry:
        """Make a user an operator of the deployment."""
        return await _or_http(grants.grant_operator(user, by=who.subject))

    @router.delete("/operators/{user}")
    async def revoke_operator(user: UserId, who: Caller = current) -> AuditEntry:
        """Stop a user being an operator."""
        return await _or_http(grants.revoke_operator(user, by=who.subject))

    @router.get("/audit")
    async def deployment_audit(
        after_seq: AfterSeq = 0, limit: Limit = 100, who: Caller = current
    ) -> list[AuditEntry]:
        """The deployment's audit log: its operators, granted and revoked."""
        return await _or_http(grants.audit(None, by=who.subject, after_seq=after_seq, limit=limit))

    @router.get("/tenants/{tenant}/audit")
    async def tenant_audit(
        tenant: TenantId, after_seq: AfterSeq = 0, limit: Limit = 100, who: Caller = current
    ) -> list[AuditEntry]:
        """A tenant's audit log after ``after_seq``, in order."""
        return await _or_http(
            grants.audit(tenant, by=by(tenant, who), after_seq=after_seq, limit=limit)
        )

    @router.get("/tenants/{tenant}/members")
    async def list_members(tenant: TenantId, who: Caller = current) -> list[Member]:
        """A tenant's members."""
        return await _or_http(grants.members(tenant, by=by(tenant, who)))

    @router.post("/tenants/{tenant}/members", status_code=201)
    async def add_member(tenant: TenantId, body: NewMember, who: Caller = current) -> AuditEntry:
        """Add a user or service principal to a tenant."""
        return await _or_http(grants.add_member(tenant, body.member, by=by(tenant, who)))

    @router.delete("/tenants/{tenant}/members/{kind}/{member_id}")
    async def remove_member(
        tenant: TenantId,
        kind: Literal["user", "service_principal"],
        member_id: str,
        who: Caller = current,
    ) -> AuditEntry:
        """Remove a member, with its grants, its places in groups and its keys."""
        member = User(id=member_id) if kind == "user" else ServicePrincipal(id=member_id)
        return await _or_http(grants.remove_member(tenant, member, by=by(tenant, who)))

    @router.get("/tenants/{tenant}/groups")
    async def list_groups(tenant: TenantId, who: Caller = current) -> dict[str, list[Member]]:
        """A tenant's groups, by id, with their members."""
        groups = await _or_http(grants.groups(tenant, by=by(tenant, who)))
        return {
            group: sorted(members, key=lambda member: (member.kind, member.id))
            for group, members in sorted(groups.items())
        }

    @router.put("/tenants/{tenant}/groups/{group}")
    async def define_group(
        tenant: TenantId, group: str, body: GroupMembers, who: Caller = current
    ) -> AuditEntry:
        """Create a group, or replace its members."""
        members = frozenset(body.members)
        return await _or_http(
            grants.define_group(tenant, Group(id=group), members, by=by(tenant, who))
        )

    @router.delete("/tenants/{tenant}/groups/{group}")
    async def delete_group(tenant: TenantId, group: str, who: Caller = current) -> AuditEntry:
        """Delete a group, with its grants."""
        return await _or_http(grants.delete_group(tenant, Group(id=group), by=by(tenant, who)))

    @router.get("/tenants/{tenant}/roles")
    async def list_roles(tenant: TenantId, who: Caller = current) -> list[Role]:
        """A tenant's custom roles."""
        return await _or_http(grants.roles(tenant, by=by(tenant, who)))

    @router.put("/tenants/{tenant}/roles/{name}")
    async def define_role(
        tenant: TenantId, name: str, body: RoleActions, who: Caller = current
    ) -> AuditEntry:
        """Create a custom role, or replace its actions."""
        role = Role(name=name, actions=frozenset(body.actions))
        return await _or_http(grants.define_role(tenant, role, by=by(tenant, who)))

    @router.delete("/tenants/{tenant}/roles/{name}")
    async def delete_role(tenant: TenantId, name: str, who: Caller = current) -> AuditEntry:
        """Delete a custom role, with its grants."""
        return await _or_http(grants.delete_role(tenant, name, by=by(tenant, who)))

    @router.get("/tenants/{tenant}/grants")
    async def list_grants(
        tenant: TenantId, workspace: WorkspaceId | None = None, who: Caller = current
    ) -> list[Grant]:
        """Every grant in a tenant, or on a workspace and the items in it."""
        return await _or_http(grants.grants_in(tenant, by=by(tenant, who), workspace=workspace))

    @router.post("/tenants/{tenant}/grants", status_code=201)
    async def grant(tenant: TenantId, body: GrantRequest, who: Caller = current) -> AuditEntry:
        """Grant a role on a resource."""
        return await _or_http(
            grants.grant(tenant, body.role, on=body.on, to=body.to, by=by(tenant, who))
        )

    @router.post("/tenants/{tenant}/revocations")
    async def revoke(tenant: TenantId, body: GrantRequest, who: Caller = current) -> AuditEntry:
        """Revoke a grant."""
        return await _or_http(
            grants.revoke(tenant, body.role, on=body.on, to=body.to, by=by(tenant, who))
        )

    @router.get("/tenants/{tenant}/restrictions")
    async def list_restrictions(
        tenant: TenantId, workspace: WorkspaceId, who: Caller = current
    ) -> list[Resource]:
        """The threads and artifacts restricted in a workspace."""
        return await _or_http(grants.restrictions(tenant, workspace, by=by(tenant, who)))

    @router.post("/tenants/{tenant}/restrictions")
    async def restrict(tenant: TenantId, body: Restriction, who: Caller = current) -> AuditEntry:
        """Restrict a thread or artifact, or lift its restriction."""
        return await _or_http(
            grants.restrict(tenant, body.on, restricted=body.restricted, by=by(tenant, who))
        )

    @router.get("/tenants/{tenant}/keys")
    async def list_keys(tenant: TenantId, who: Caller = current) -> list[KeyView]:
        """A tenant's keys: their ids and principals, never their secrets."""
        keys = await _or_http(grants.keys(tenant, by=by(tenant, who)))
        return [KeyView(id=key.id, principal=key.principal) for key in keys]

    @router.post("/tenants/{tenant}/keys", status_code=201)
    async def issue_key(tenant: TenantId, body: NewKey, who: Caller = current) -> IssuedKey:
        """Issue a key for a service principal. The key is in this response, and nowhere else."""
        principal = ServicePrincipal(id=body.principal)
        key, entry = await _or_http(grants.issue_key(tenant, principal, by=by(tenant, who)))
        return IssuedKey(key=key, entry=entry)

    @router.delete("/tenants/{tenant}/keys/{key_id}")
    async def revoke_key(tenant: TenantId, key_id: str, who: Caller = current) -> AuditEntry:
        """Revoke a key."""
        return await _or_http(grants.revoke_key(tenant, key_id, by=by(tenant, who)))

    return router


def _refusal(code: str, message: str) -> HTTPException:
    detail: dict[str, Any] = {"type": code, "message": message}
    return HTTPException(status_code=STATUS_CODES[code], detail=detail)


def _refused(error: GrantrError) -> HTTPException:
    return _refusal("forbidden" if isinstance(error, Forbidden) else "invalid", str(error))


async def _or_http[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except (Forbidden, Invalid) as error:
        raise _refused(error) from error
