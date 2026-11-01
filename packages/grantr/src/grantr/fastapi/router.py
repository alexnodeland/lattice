"""The admin API, and the two reads UIs ask.

Tenants, members, groups, roles, grants, keys, integrations and the audit log; and ``/me``,
``/checks``, and which integrations are on in a workspace. And approvals: those a person may
answer, each one as it stands, and their answer (grantr ADR-0040). And bindings: which of a
source's events reach which workspace (grantr ADR-0041).
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, Final, Literal, NamedTuple

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    TypeAdapter,
    ValidationError,
)
from starlette.requests import HTTPConnection

from grantr.core import (
    TENANT,
    Agent,
    AuditEntry,
    AuditFilter,
    AuditType,
    CatalogView,
    Connection,
    Forbidden,
    Grant,
    Grantee,
    GrantrError,
    Group,
    IntegrationState,
    Invalid,
    Member,
    Membership,
    PrincipalId,
    Resource,
    Role,
    RulePrincipal,
    ServicePrincipal,
    SettingState,
    SettingsView,
    Stale,
    Subject,
    TenantId,
    User,
    UserId,
    WorkspaceId,
)
from grantr.core.roles import MANAGE_SETTINGS
from grantr.grants import Grants
from lattice_core.approvals import (
    Answer,
    Approval,
    ApprovalId,
    ApprovalRequest,
    DigestMismatch,
    NotAnAnswerer,
    NotPending,
    State,
    UnknownApproval,
)
from lattice_core.approvals import Subject as Answerer
from lattice_core.bindings import Binding, Trust
from lattice_core.capabilities import Scope


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
    "version_conflict": 409,
    "not_found": 404,
    "invalid_state": 409,
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


class IntegrationSwitch(BaseModel):
    """An integration's new setting, on the tenant or in a workspace, as its path names."""

    on: bool | None
    """On, off, or ``null`` to unset it, so it inherits the level above."""


class SettingChange(BaseModel):
    """A setting's new value on the tenant or in a workspace, as its path names."""

    value: StrictInt | list[StrictStr] | None
    """A whole number or names, no wider than the layer above's; ``null`` to unset it."""


class ApprovalAnswerer(Answerer):
    """Who answered an approval: a person, or a service principal, by their grantr id.

    lattice-core's answerer, named apart from grantr's own subjects in the API's document.
    """


class AnswerGiven(Answer):
    """An approval's answer as grantr recorded it: who gave it, and when."""

    by: ApprovalAnswerer
    """Who answered."""
    at: AwareDatetime
    """When it was answered."""


class ApprovalView(ApprovalRequest):
    """An approval as it stands: lattice-core's ``Approval``, as the API's document names it.

    Its fields are the approval's, which a test holds equal; only its answerer's model is named
    apart from grantr's own subjects.
    """

    id: ApprovalId
    """Its id."""
    asked_at: AwareDatetime
    """When it was asked."""
    state: State
    """Where it stands."""
    answer: AnswerGiven | None = None
    """The answer that settled it, if one did."""
    reason: str | None = None
    """Why it expired or was withdrawn."""
    taken_at: AwareDatetime | None = None
    """When the one call it lets through went ahead, if one has."""


def _view(approval: Approval) -> ApprovalView:
    return ApprovalView.model_validate(approval.model_dump())


class ApprovalAnswer(BaseModel):
    """An answer to an approval, as a person gives it in portalr."""

    model_config = ConfigDict(frozen=True)

    approved: bool
    """Whether it approves the call."""
    arguments_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    """The digest of the arguments the person was shown, as the approval gives it; an answer
    to other arguments is refused."""
    reason: str | None = Field(default=None, max_length=2000)
    """Why, in the person's words, if they gave one."""
    surface: Literal["portalr", "portalr:confirm"] = "portalr"
    """Where it was given: portalr's approval page, or its confirm page, the one surface a
    caller's own confirmation is answered on."""


class NewBinding(BaseModel):
    """A source's connection to bind to one of the tenant's workspaces (lattice ADR-0040)."""

    workspace: WorkspaceId
    source: str
    """The source's name, as its spec names it: ``tracker``, ``forge``."""
    connection: str
    """The id of the source's connection."""
    select: dict[str, Any] = {}
    """What it selects by, in the source's declared selectors; empty selects everything."""
    types: list[str] | None = None
    """The event types it receives; ``null`` for every type the source has."""
    trust: Trust | None = None
    """The level it lowers the source's to; ``null`` keeps the source's."""
    options: dict[str, Any] = {}
    """The source's own options, such as a tracker's default labels."""


class NewKey(BaseModel):
    """The service principal a key is issued to."""

    principal: PrincipalId


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

BeforeSeq = Annotated[int | None, Query(ge=0)]
"""Read the audit entries before this sequence number."""

Limit = Annotated[int | None, Query(ge=1, le=1000)]
"""Read the first this many audit entries: 100 with neither this nor ``last``."""

Last = Annotated[int | None, Query(ge=1, le=1000)]
"""Read the last this many audit entries, still oldest first."""

ActorKind = Literal["user", "service_principal", "rule", "agent"]
"""The kinds of subject that make changes to access."""

_MEMBER: TypeAdapter[Member] = TypeAdapter(Member)


def _invalid(field: str, message: str, given: object) -> RequestValidationError:
    """A 422 for a query parameter, as FastAPI words its own."""
    return RequestValidationError(
        [{"type": "value_error", "loc": ("query", field), "msg": message, "input": given}]
    )


def _actor(kind: ActorKind | None, id: str | None, workspace: str | None) -> Subject | None:
    """The subject the actor parameters name, or None for anyone; a 422 if they name none."""
    match kind:
        case None if id is None and workspace is None:
            return None
        case None:
            raise _invalid("actor_kind", "actor_kind is required with actor or workspace", kind)
        case "agent" if id is None and workspace is None:
            return Agent()
        case "rule" if id is not None and workspace is not None:
            return RulePrincipal(workspace=workspace, rule=id)
        case "user" | "service_principal" if id is not None and workspace is None:
            try:
                return _MEMBER.validate_python({"kind": kind, "id": id})
            except ValidationError as error:
                raise _invalid("actor", str(error.errors()[0]["msg"]), id) from error
        case _:
            wants = {
                "agent": "neither actor nor workspace",
                "rule": "actor, the rule's name, and workspace",
                "user": "actor, and no workspace",
                "service_principal": "actor, and no workspace",
            }[kind]
            raise _invalid("actor", f"actor_kind {kind} takes {wants}", id)


def audit_filter(
    types: Annotated[
        list[AuditType] | None,
        Query(alias="type", description="Keep only entries of these event types; it may repeat."),
    ] = None,
    actor_kind: Annotated[
        ActorKind | None,
        Query(description="Keep only the changes of one subject, of this kind."),
    ] = None,
    actor: Annotated[
        str | None,
        Query(
            min_length=1,
            description="That subject's id: a user's or a service principal's, or a rule's name.",
        ),
    ] = None,
    workspace: Annotated[
        str | None,
        Query(min_length=1, description="A rule's workspace, with `actor_kind=rule`."),
    ] = None,
) -> AuditFilter:
    """Which entries a read of the audit log keeps, from its query."""
    return AuditFilter(types=frozenset(types or ()), by=_actor(actor_kind, actor, workspace))


Kept = Annotated[AuditFilter, Depends(audit_filter)]
"""The entries a read of the audit log keeps."""


TenantHeader = Annotated[TenantId | None, Header(alias="X-Tenant")]
"""The tenant a request to ``/me`` or ``/checks`` names."""

IfMatch = Annotated[str | None, Header(alias="If-Match")]
"""The version of a setting the caller read, as an entity tag: `"3"`. Omitted, the last write
wins; `*` names no version, and is refused."""


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

    approvals = grants.approvals()

    async def answerer(tenant: TenantId, who: Caller) -> Answerer:
        """The caller as an approval's answerer, if a member of the tenant."""
        _, member = await active(who, tenant)
        return Answerer(id=member.id, service=isinstance(member, ServicePrincipal))

    async def shown(tenant: TenantId, id: ApprovalId, subject: Answerer) -> Approval:
        """The tenant's approval, to one who may see it; a 404 for anyone else."""
        try:
            approval = await approvals.shown(id, subject)
        except UnknownApproval as error:
            raise _refusal("not_found", f"no approval {id}") from error
        if approval.scope.tenant_id != tenant:
            raise _refusal("not_found", f"no approval {id}")
        return approval

    @router.get("/catalog", dependencies=[current])
    async def catalog() -> CatalogView:
        """The built-in roles a tenant's admins grant, and what a custom role may hold.

        Each built-in role comes with where it may be granted. It is the deployment's; any
        caller may read it.
        """
        return grants.catalog()

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
        keep: Kept,
        after_seq: AfterSeq = 0,
        before_seq: BeforeSeq = None,
        limit: Limit = None,
        last: Last = None,
        who: Caller = current,
    ) -> list[AuditEntry]:
        """The deployment's audit log: its operators, granted and revoked.

        ``type`` keeps only some types of entry, and ``actor_kind``, ``actor`` and ``workspace``
        one subject's changes. It reads the window ``after_seq < seq < before_seq``: the first
        ``limit``, or the last ``last``, oldest first; a client pages back with ``last`` and its
        oldest entry's ``seq`` as ``before_seq``.
        """
        return await _or_http(
            grants.audit(
                None,
                by=who.subject,
                after_seq=after_seq,
                before_seq=before_seq,
                limit=limit,
                last=last,
                keep=keep,
            )
        )

    @router.get("/tenants/{tenant}/audit")
    async def tenant_audit(
        tenant: TenantId,
        keep: Kept,
        after_seq: AfterSeq = 0,
        before_seq: BeforeSeq = None,
        limit: Limit = None,
        last: Last = None,
        who: Caller = current,
    ) -> list[AuditEntry]:
        """A tenant's audit log in the window ``after_seq < seq < before_seq``, oldest first.

        ``type`` keeps only some types of entry, and ``actor_kind``, ``actor`` and ``workspace``
        one subject's changes. It reads the window ``after_seq < seq < before_seq``: the first
        ``limit``, or the last ``last``, oldest first; a client pages back with ``last`` and its
        oldest entry's ``seq`` as ``before_seq``.
        """
        return await _or_http(
            grants.audit(
                tenant,
                by=by(tenant, who),
                after_seq=after_seq,
                before_seq=before_seq,
                limit=limit,
                last=last,
                keep=keep,
            )
        )

    @router.get("/tenants/{tenant}/members")
    async def list_members(tenant: TenantId, who: Caller = current) -> list[Member]:
        """A tenant's members."""
        return await _or_http(grants.members(tenant, by=by(tenant, who)))

    @router.post("/tenants/{tenant}/members", status_code=201)
    async def add_member(tenant: TenantId, body: NewMember, who: Caller = current) -> AuditEntry:
        """Add a user or service principal to a tenant."""
        return await _or_http(grants.add_member(tenant, body.member, by=by(tenant, who)))

    @router.delete("/tenants/{tenant}/members/user/{member_id}")
    async def remove_user(tenant: TenantId, member_id: UserId, who: Caller = current) -> AuditEntry:
        """Remove a user, with their grants and their places in groups."""
        member = User(id=member_id)
        return await _or_http(grants.remove_member(tenant, member, by=by(tenant, who)))

    @router.delete("/tenants/{tenant}/members/service_principal/{member_id}")
    async def remove_principal(
        tenant: TenantId, member_id: PrincipalId, who: Caller = current
    ) -> AuditEntry:
        """Remove a service principal, with its grants, its places in groups and its keys."""
        member = ServicePrincipal(id=member_id)
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

    @router.get("/tenants/{tenant}/integrations")
    async def tenant_integrations(
        tenant: TenantId, who: Caller = current
    ) -> list[IntegrationState]:
        """Every integration as it is set on a tenant, and whether it is on where unset."""
        return await _or_http(grants.integrations(tenant, by=by(tenant, who)))

    @router.put("/tenants/{tenant}/integrations/{key}")
    async def set_tenant_integration(
        tenant: TenantId, key: str, body: IntegrationSwitch, who: Caller = current
    ) -> IntegrationState:
        """Turn an integration on or off on a tenant, or unset it with null.

        Setting what is set already changes nothing, and records nothing.
        """
        return await _or_http(grants.set_integration(tenant, key, body.on, by=by(tenant, who)))

    # A workspace's id may hold a slash, as a path does. Each route below ends in segments of
    # its own, and a key holds no slash, so a path matches one of them, however the id reads.
    @router.get("/tenants/{tenant}/workspaces/{workspace:path}/integrations")
    async def workspace_integrations(
        tenant: TenantId, workspace: WorkspaceId, who: Caller = current
    ) -> list[IntegrationState]:
        """Every integration as it is set in a workspace and on its tenant, and whether it is on."""
        return await _or_http(grants.integrations(tenant, workspace=workspace, by=by(tenant, who)))

    @router.put("/tenants/{tenant}/workspaces/{workspace:path}/integrations/{key}")
    async def set_workspace_integration(
        tenant: TenantId,
        workspace: WorkspaceId,
        key: str,
        body: IntegrationSwitch,
        who: Caller = current,
    ) -> IntegrationState:
        """Turn an integration on or off in a workspace, or unset it with null.

        Setting what is set already changes nothing, and records nothing.
        """
        return await _or_http(
            grants.set_integration(tenant, key, body.on, workspace=workspace, by=by(tenant, who))
        )

    @router.get("/tenants/{tenant}/workspaces/{workspace:path}/enabled-integrations")
    async def enabled_integrations(
        tenant: TenantId, workspace: WorkspaceId, who: Caller = current
    ) -> dict[str, bool]:
        """Whether each integration is on in a workspace, by key, for whoever can open it."""
        return await _or_http(grants.integrations_enabled(tenant, workspace, by=by(tenant, who)))

    @router.get("/tenants/{tenant}/settings")
    async def tenant_settings(tenant: TenantId, who: Caller = current) -> SettingsView:
        """Every setting as it is narrowed on a tenant: each layer, the ceiling, the outcome."""
        return await _or_http(grants.settings(tenant, by=by(tenant, who)))

    async def manages_tenant(tenant: TenantId, who: Caller = current) -> Subject:
        """The caller, if it may narrow the tenant's settings: before its body is read."""
        subject = by(tenant, who)
        if not await grants.check(tenant, subject, MANAGE_SETTINGS, TENANT):
            raise _refused(Forbidden(f"{MANAGE_SETTINGS} on the tenant is refused"))
        return subject

    async def manages_workspace(
        tenant: TenantId, workspace: WorkspaceId, who: Caller = current
    ) -> Subject:
        """The caller, if it may narrow the workspace's settings: before its body is read."""
        subject = by(tenant, who)
        on = Resource(kind="workspace", workspace=workspace)
        if not workspace or not await grants.check(tenant, subject, MANAGE_SETTINGS, on):
            raise _refused(Forbidden(f"{MANAGE_SETTINGS} on the workspace is refused"))
        return subject

    def named_version(if_match: IfMatch = None) -> int | None:
        """The version `If-Match` names: read once the caller may, so it learns nothing first."""
        return _version(if_match)

    # Each is asked before the body is validated, and in this order.
    tenant_manager = Depends(manages_tenant)
    workspace_manager = Depends(manages_workspace)
    version_named = Depends(named_version)

    @router.put("/tenants/{tenant}/settings/{key}")
    async def set_tenant_setting(
        tenant: TenantId,
        key: str,
        body: SettingChange,
        response: Response,
        subject: Subject = tenant_manager,
        version: int | None = version_named,
    ) -> SettingState:
        """Narrow a setting on a tenant, or unset it with null.

        `If-Match` names the version of the tenant's setting the caller read, `"0"` for one never
        set: another is refused with 409; omitted, the last write wins. A value wider than the
        layer above is refused with 422, saying how wide it may be and which layer says so. A
        caller who may not is refused with 403 before its body or `If-Match` is read.
        """
        state = await _or_http(
            grants.set_setting(tenant, key, body.value, version=version, by=subject)
        )
        response.headers["ETag"] = f'"{state.version}"'
        return state

    @router.get("/tenants/{tenant}/workspaces/{workspace:path}/settings")
    async def workspace_settings(
        tenant: TenantId, workspace: WorkspaceId, who: Caller = current
    ) -> SettingsView:
        """Every setting as it is narrowed in a workspace and on its tenant, and the outcome."""
        return await _or_http(grants.settings(tenant, workspace=workspace, by=by(tenant, who)))

    @router.put("/tenants/{tenant}/workspaces/{workspace:path}/settings/{key}")
    async def set_workspace_setting(
        tenant: TenantId,
        workspace: WorkspaceId,
        key: str,
        body: SettingChange,
        response: Response,
        subject: Subject = workspace_manager,
        version: int | None = version_named,
    ) -> SettingState:
        """Narrow a setting in a workspace, or unset it with null, as on the tenant."""
        state = await _or_http(
            grants.set_setting(
                tenant, key, body.value, version=version, workspace=workspace, by=subject
            )
        )
        response.headers["ETag"] = f'"{state.version}"'
        return state

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

    @router.get("/tenants/{tenant}/approvals")
    async def list_approvals(
        tenant: TenantId,
        workspace: Annotated[
            WorkspaceId | None,
            Query(description="Only those asked in this workspace; in every one if omitted."),
        ] = None,
        who: Caller = current,
    ) -> list[ApprovalView]:
        """The approvals pending in the tenant that the caller may answer, oldest first."""
        subject = await answerer(tenant, who)
        if workspace is None:
            asked = await approvals.answerable(tenant, subject)
        else:
            asked = await approvals.pending(
                Scope(tenant_id=tenant, workspace_id=workspace), subject
            )
        return [_view(approval) for approval in asked]

    @router.get("/tenants/{tenant}/approvals/{approval}")
    async def read_approval(
        tenant: TenantId, approval: ApprovalId, who: Caller = current
    ) -> ApprovalView:
        """An approval as it stands, for one who may answer it or the person it was asked for.

        Anyone else is told it isn't there.
        """
        return _view(await shown(tenant, approval, await answerer(tenant, who)))

    @router.post("/tenants/{tenant}/approvals/{approval}/answer")
    async def answer_approval(
        tenant: TenantId, approval: ApprovalId, body: ApprovalAnswer, who: Caller = current
    ) -> ApprovalView:
        """Answer a pending approval as the caller, and return it settled.

        The first answer wins: a later one, or one past the deadline, is a 409 (`invalid_state`),
        and the approval, read again, shows the first. An answer to other arguments than the
        approval's is a 409 (`version_conflict`). A caller who may see it but not answer it, or
        not on that surface, is refused; a caller's own confirmation is answered on
        `portalr:confirm` alone.
        """
        subject = await answerer(tenant, who)
        await shown(tenant, approval, subject)
        answer = Answer(
            approved=body.approved,
            arguments_digest=body.arguments_digest,
            surface=body.surface,
            reason=body.reason,
        )
        try:
            return _view(await approvals.answer(approval, answer, subject=subject))
        except NotPending as error:
            raise _refusal("invalid_state", str(error)) from error
        except NotAnAnswerer as error:
            raise _refusal("forbidden", str(error)) from error
        except DigestMismatch as error:
            raise _refusal("version_conflict", str(error)) from error

    @router.get("/tenants/{tenant}/bindings")
    async def list_bindings(
        tenant: TenantId,
        workspace: Annotated[
            WorkspaceId | None,
            Query(description="Only those reaching this workspace; every one if omitted."),
        ] = None,
        who: Caller = current,
    ) -> list[Binding]:
        """The bindings that reach the tenant's workspaces, with ``grantr:manage_bindings``.

        The operator's come first, read only, then the tenant's.
        """
        bindings = grants.bindings()
        return await _or_http(bindings.listed(tenant, by=by(tenant, who), workspace=workspace))

    @router.post("/tenants/{tenant}/bindings", status_code=201)
    async def bind(tenant: TenantId, body: NewBinding, who: Caller = current) -> AuditEntry:
        """Bind a source's connection to one of the tenant's workspaces."""
        return await _or_http(
            grants.bindings().bind(
                tenant,
                body.workspace,
                body.source,
                body.connection,
                select=body.select,
                types=body.types,
                trust=body.trust,
                options=body.options,
                by=by(tenant, who),
            )
        )

    @router.delete("/tenants/{tenant}/bindings/{binding}")
    async def unbind(tenant: TenantId, binding: str, who: Caller = current) -> AuditEntry:
        """Remove one of the tenant's bindings; the operator's are the deployment's to change."""
        return await _or_http(grants.bindings().unbind(tenant, binding, by=by(tenant, who)))

    @router.get("/tenants/{tenant}/connections")
    async def list_connections(
        tenant: TenantId,
        user: Annotated[
            UserId | None,
            Query(description="Only this person's; theirs, or every one for an admin, if omitted."),
        ] = None,
        who: Caller = current,
    ) -> list[Connection]:
        """The outside clients connected to the tenant that the caller may read, oldest first.

        A member reads their own, with ``grantr:read_connections``; whoever adds the tenant's
        members, every one (grantr ADR-0043). Revoked ones are listed too.
        """
        listed = grants.connections().listed(tenant, by=by(tenant, who), user=user)
        return await _or_http(listed)

    @router.delete("/tenants/{tenant}/connections/{connection}")
    async def revoke_connection(
        tenant: TenantId, connection: str, who: Caller = current
    ) -> AuditEntry:
        """Revoke a connection: its next call is refused.

        A member revokes their own, with ``grantr:revoke_connection``; whoever adds the
        tenant's members, any.
        """
        revoked = grants.connections().revoke(tenant, connection, by=by(tenant, who))
        return await _or_http(revoked)

    return router


def _refusal(code: str, message: str) -> HTTPException:
    detail: dict[str, Any] = {"type": code, "message": message}
    return HTTPException(status_code=STATUS_CODES[code], detail=detail)


def _refused(error: GrantrError) -> HTTPException:
    if isinstance(error, Stale):
        return _refusal("version_conflict", str(error))
    return _refusal("forbidden" if isinstance(error, Forbidden) else "invalid", str(error))


def _version(if_match: str | None) -> int | None:
    """The version an `If-Match` names, quoted or not; a 422 for anything else."""
    if if_match is None:
        return None
    tag = if_match.strip().removeprefix("W/").strip('"')
    if not tag.isdigit() or len(tag) > 9:
        raise _refusal("invalid", "If-Match names a version: a whole number, quoted")
    return int(tag)


async def _or_http[T](awaitable: Awaitable[T]) -> T:
    try:
        return await awaitable
    except (Forbidden, Invalid, Stale) as error:
        raise _refused(error) from error
