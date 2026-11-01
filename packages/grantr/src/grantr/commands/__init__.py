"""grantr's commands: every action on access, declared once for every surface (lattice RFC-0014).

:data:`CATALOG` is grantr's static catalog, lattice-core's ``Commands``: members, groups, roles,
grants, restrictions, keys, integrations, settings, the audit log, approvals' reads, the tenant
and the deployment's operators, each a ``command`` capability named ``grantr.<name>``, gated by
the grantr action grantr's own method asks (grantr ADR-0042).

:func:`provider` binds it to a :class:`~grantr.grants.Grants` at the application's composition
root: lattice-core's ``Provider``, whose ``call`` runs each command as the subject the call is
for (:func:`~grantr.grants.calls.subject_of_call`), in the call's tenant, so grantr checks it
again as it does every command. Each answers JSON text.

- **`admin_high`:** deleting the tenant, revoking a key, granting a role on the tenant, defining
  a role (whose actions are known only as it is called), granting the operator role and revoking
  another member's connection. Each asks its caller's own confirmation through the enforcer's
  policy (lattice ADR-0038).
- **Connections** (grantr ADR-0043): a member lists and revokes their own; revoking another's,
  for whoever adds the tenant's members, is a command of its own, ``admin_high``.
- **Not exposed:** answering an approval, which comes from a person (lattice RFC-0014), and
  issuing a key, whose secret is shown once, to the person who issues it, in portalr: neither is
  a tool a model can call.
"""

import json
from collections.abc import Awaitable, Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from grantr.core import (
    TENANT,
    AuditFilter,
    AuditType,
    Grantee,
    Group,
    Member,
    PrincipalId,
    Resource,
    Role,
    ServicePrincipal,
    Subject,
    User,
    UserId,
)
from grantr.grants import Grants
from grantr.grants.calls import subject_of_call
from lattice_core.approvals import Subject as Answerer
from lattice_core.bindings import Trust
from lattice_core.capabilities import (
    CallContext,
    Capability,
    Effect,
    Gate,
    JsonObject,
    ProviderKind,
    Reversibility,
    Scope,
    Tier,
    ToolResult,
)
from lattice_core.commands import Command, Exposure, NotExposed, Surface, Toolset

__all__ = ["ADMIN_HIGH", "CATALOG", "VERSION", "GrantrCommands", "GrantrProvider", "provider"]

VERSION: Final = "1.0.0"
"""Each command's version."""

ADMIN = "/portalr/admin/t/{tenant}"
"""portalr's admin, for a tenant: where each command's route starts."""


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)


class _Nothing(_Arguments):
    pass


class _InWorkspace(_Arguments):
    workspace: str | None = None
    """Only in this workspace; on the tenant, or in every workspace, if omitted."""


class _Member(_Arguments):
    member: Member
    """The user or service principal."""


class _Group(_Arguments):
    group: str = Field(min_length=1)
    """The group's name."""
    members: list[Member]
    """Its members, which replace any it had."""


class _GroupName(_Arguments):
    group: str = Field(min_length=1)
    """The group's name."""


class _Role(_Arguments):
    name: str = Field(min_length=1)
    """The custom role's name."""
    actions: list[str]
    """The actions it holds, which replace any it held."""


class _RoleName(_Arguments):
    name: str = Field(min_length=1)
    """The custom role's name."""


class _Grant(_Arguments):
    role: str
    """The role to grant or revoke."""
    on: Resource
    """Where: a workspace, a thread, an artifact or a rule. The tenant's roles are granted by
    ``grantr.grant_on_tenant``."""
    to: Grantee
    """To whom: a user, a service principal, a group or a rule."""


class _TenantGrant(_Arguments):
    role: str
    """The role to grant on the tenant: owner, admin, or a custom role."""
    to: Grantee
    """To whom."""


class _Restrict(_Arguments):
    on: Resource
    """The thread or artifact."""
    restricted: bool = True
    """Whether only those granted a role on it may open it."""


class _Key(_Arguments):
    key: str = Field(min_length=1)
    """The key's public id."""


class _Connections(_Arguments):
    user: UserId | None = None
    """Only this person's; yours, or every one for an admin, if omitted."""


class _Connection(_Arguments):
    connection: str = Field(min_length=1)
    """The connection's id, such as ``con_0123456789abcdef``."""


class _NewKey(_Arguments):
    principal: PrincipalId
    """The service principal the key is for."""


class _Integration(_Arguments):
    key: str
    """The integration's key."""
    on: bool | None
    """On, off, or null to unset it, so it inherits the level above."""
    workspace: str | None = None
    """In this workspace; on the tenant if omitted."""


class _Setting(_Arguments):
    key: str
    """The setting's key."""
    value: int | list[str] | None
    """A whole number or names, within the layer above's; null to unset it."""
    workspace: str | None = None
    """In this workspace; on the tenant if omitted."""
    version: int | None = None
    """The version read, so a change made since is refused; the last write wins if omitted."""


class _Audit(_Arguments):
    last: int = Field(default=100, ge=1, le=1000)
    """How many of the newest entries to read, oldest first."""
    types: list[AuditType] = []
    """Only entries of these types; every type if empty."""


class _Approval(_Arguments):
    approval: str = Field(min_length=1)
    """The approval's id."""


class _Answer(_Approval):
    approved: bool
    """Whether it approves the call."""
    arguments_digest: str
    """The digest of the arguments shown."""


class _Restrictions(_Arguments):
    workspace: str = Field(min_length=1)
    """The workspace whose restricted threads and artifacts to list."""


class _Bind(_Arguments):
    workspace: str = Field(min_length=1)
    """The tenant's workspace the source's events reach."""
    source: str
    """The event source, by its name."""
    connection: str
    """The source's connection the events come from, such as an app's installation."""
    select: JsonObject | None = None
    """Which of the connection's events, as the source reads a selection; every one if omitted."""
    types: list[str] | None = None
    """Only events of these types; every type the source has if omitted."""
    trust: Trust | None = None
    """How far the events are trusted; the source's own trust if omitted."""
    options: JsonObject | None = None
    """The source's own options for the binding."""


class _Binding(_Arguments):
    binding: str = Field(min_length=1)
    """The binding's id."""


class _Operator(_Arguments):
    user: UserId
    """The user."""


type _Handler = Callable[[Grants, Any, str, Subject], Awaitable[JsonValue]]


@dataclass(frozen=True)
class _Spec:
    name: str
    description: str
    action: str
    arguments: type[_Arguments]
    handler: _Handler
    tier: Tier = "write"
    reversibility: Reversibility = "compensable"
    effects: frozenset[Effect] = frozenset()
    admin_high: bool = False
    toolset: Toolset = "admin"
    exposure: Exposure | NotExposed = "tool"
    route: str | None = None
    surfaces: frozenset[Surface] = frozenset({"portalr", "mcp", "acp", "webmcp"})


def _dumped(value: BaseModel) -> JsonValue:
    dumped: JsonValue = value.model_dump(mode="json")
    return dumped


def _all(values: Iterable[BaseModel]) -> JsonValue:
    return [_dumped(value) for value in values]


def _read(
    name: str, description: str, action: str, route: str | None, handler: _Handler, **more: Any
) -> _Spec:
    return _Spec(
        name,
        description,
        action,
        more.pop("arguments", _Nothing),
        handler,
        tier="read",
        reversibility="none",
        effects=frozenset({"reads_private"}),
        route=route,
        **more,
    )


def _not_a_tenant(on: Resource) -> Resource:
    if on.kind in ("tenant", "deployment"):
        raise ValueError("a role on the tenant is granted by grantr.grant_on_tenant")
    return on


def _answerer(subject: Subject) -> Answerer:
    if isinstance(subject, User | ServicePrincipal):
        return Answerer(id=subject.id, service=isinstance(subject, ServicePrincipal))
    raise ValueError("only a member reads an approval")


async def _list_approvals(g: Grants, a: _InWorkspace, tenant: str, by: Subject) -> JsonValue:
    approvals = g.approvals()
    if a.workspace is None:
        return _all(await approvals.answerable(tenant, _answerer(by)))
    scope = Scope(tenant_id=tenant, workspace_id=a.workspace)
    return _all(await approvals.pending(scope, _answerer(by)))


async def _read_approval(g: Grants, a: _Approval, tenant: str, by: Subject) -> JsonValue:
    approval = await g.approvals().shown(a.approval, _answerer(by))
    if approval.scope.tenant_id != tenant:
        raise ValueError(f"no approval {a.approval}")
    return _dumped(approval)


async def _refused(_g: Grants, _a: _Arguments, _tenant: str, _by: Subject) -> JsonValue:
    raise ValueError("this command isn't called through the enforcer: it is portalr's alone")


async def _entry(made: Awaitable[BaseModel]) -> JsonValue:
    return _dumped(await made)


async def _one(read: Awaitable[BaseModel]) -> JsonValue:
    return _dumped(await read)


async def _listed(read: Awaitable[Sequence[BaseModel]]) -> JsonValue:
    return _all(await read)


async def _all_members(g: Grants, tenant: str, by: Subject) -> JsonValue:
    return [member.model_dump(mode="json") for member in await g.members(tenant, by=by)]


async def _all_groups(g: Grants, tenant: str, by: Subject) -> JsonValue:
    groups = await g.groups(tenant, by=by)
    return {
        name: sorted(
            (member.model_dump(mode="json") for member in members),
            key=lambda member: json.dumps(member, sort_keys=True),
        )
        for name, members in sorted(groups.items())
    }


_SPECS: Final[tuple[_Spec, ...]] = (
    _read(
        "grantr.list_members",
        "List the tenant's members: its users and service principals.",
        "grantr:add_member",
        f"{ADMIN}/access/members",
        lambda g, _a, t, by: _all_members(g, t, by),
    ),
    _Spec(
        "grantr.add_member",
        "Add a user or service principal to the tenant, holding no role until one is granted.",
        "grantr:add_member",
        _Member,
        lambda g, a, t, by: _entry(g.add_member(t, a.member, by=by)),
        route=f"{ADMIN}/access/members",
    ),
    _Spec(
        "grantr.remove_member",
        "Remove a member from the tenant, with every grant made to them in it.",
        "grantr:remove_member",
        _Member,
        lambda g, a, t, by: _entry(g.remove_member(t, a.member, by=by)),
        route=f"{ADMIN}/access/members",
    ),
    _read(
        "grantr.list_groups",
        "List the tenant's groups and their members.",
        "grantr:manage_groups",
        f"{ADMIN}/access/groups",
        lambda g, _a, t, by: _all_groups(g, t, by),
    ),
    _Spec(
        "grantr.define_group",
        "Define a group of the tenant's members, or replace its members.",
        "grantr:manage_groups",
        _Group,
        lambda g, a, t, by: _entry(
            g.define_group(t, Group(id=a.group), frozenset(a.members), by=by)
        ),
        route=f"{ADMIN}/access/groups",
    ),
    _Spec(
        "grantr.delete_group",
        "Delete a group, with every grant made to it.",
        "grantr:manage_groups",
        _GroupName,
        lambda g, a, t, by: _entry(g.delete_group(t, Group(id=a.group), by=by)),
        route=f"{ADMIN}/access/groups",
    ),
    _read(
        "grantr.list_roles",
        "List the tenant's custom roles and the actions each holds.",
        "grantr:define_role",
        f"{ADMIN}/access/roles",
        lambda g, _a, t, by: _listed(g.roles(t, by=by)),
    ),
    _Spec(
        "grantr.define_role",
        "Define a custom role of the tenant, or replace its actions. It asks your confirmation.",
        "grantr:define_role",
        _Role,
        lambda g, a, t, by: _entry(
            g.define_role(t, Role(name=a.name, actions=frozenset(a.actions)), by=by)
        ),
        admin_high=True,
        route=f"{ADMIN}/access/roles",
    ),
    _Spec(
        "grantr.delete_role",
        "Delete a custom role that no grant names.",
        "grantr:define_role",
        _RoleName,
        lambda g, a, t, by: _entry(g.delete_role(t, a.name, by=by)),
        route=f"{ADMIN}/access/roles",
    ),
    _read(
        "grantr.list_grants",
        "List the grants made in the tenant, or in one of its workspaces.",
        "grantr:grant",
        f"{ADMIN}/access/grants",
        lambda g, a, t, by: _listed(g.grants_in(t, by=by, workspace=a.workspace)),
        arguments=_InWorkspace,
    ),
    _Spec(
        "grantr.grant",
        "Grant a role on a workspace, thread, artifact or rule to a member, group or rule.",
        "grantr:grant",
        _Grant,
        lambda g, a, t, by: _entry(g.grant(t, a.role, on=_not_a_tenant(a.on), to=a.to, by=by)),
        route=f"{ADMIN}/access/grants",
    ),
    _Spec(
        "grantr.grant_on_tenant",
        "Grant a role on the whole tenant, such as owner or admin. It asks your confirmation.",
        "grantr:grant",
        _TenantGrant,
        lambda g, a, t, by: _entry(g.grant(t, a.role, on=TENANT, to=a.to, by=by)),
        admin_high=True,
        route=f"{ADMIN}/access/grants",
    ),
    _Spec(
        "grantr.revoke",
        "Revoke a role granted on the tenant, a workspace, a thread, an artifact or a rule.",
        "grantr:revoke",
        _Grant,
        lambda g, a, t, by: _entry(g.revoke(t, a.role, on=a.on, to=a.to, by=by)),
        route=f"{ADMIN}/access/grants",
    ),
    _read(
        "grantr.list_restrictions",
        "List the threads and artifacts restricted in a workspace.",
        "grantr:restrict",
        None,
        lambda g, a, t, by: _listed(g.restrictions(t, a.workspace, by=by)),
        arguments=_Restrictions,
    ),
    _Spec(
        "grantr.restrict",
        "Restrict a thread or artifact to those granted a role on it, or lift the restriction.",
        "grantr:restrict",
        _Restrict,
        lambda g, a, t, by: _entry(g.restrict(t, a.on, restricted=a.restricted, by=by)),
        route=None,
    ),
    _read(
        "grantr.list_keys",
        "List the tenant's keys by their public ids, never their secrets.",
        "grantr:issue_key",
        f"{ADMIN}/access/keys",
        lambda g, _a, t, by: _listed(g.keys(t, by=by)),
    ),
    _Spec(
        "grantr.issue_key",
        "Issue a key to a service principal; its secret is shown once.",
        "grantr:issue_key",
        _NewKey,
        _refused,
        exposure=NotExposed(reason="a key's secret is shown once, to who issues it, in portalr"),
        route=f"{ADMIN}/access/keys",
        surfaces=frozenset({"portalr"}),
    ),
    _Spec(
        "grantr.revoke_key",
        "Revoke a key at once: whatever holds it is refused. It asks your confirmation.",
        "grantr:revoke_key",
        _Key,
        lambda g, a, t, by: _entry(g.revoke_key(t, a.key, by=by)),
        reversibility="irreversible",
        admin_high=True,
        route=f"{ADMIN}/access/keys",
    ),
    _read(
        "grantr.list_connections",
        "List the outside clients connected to the tenant that you may read, revoked ones too: "
        "your own, or every one if you add the tenant's members.",
        "grantr:read_connections",
        f"{ADMIN}/access/connections",
        lambda g, a, t, by: _listed(g.connections().listed(t, by=by, user=a.user)),
        arguments=_Connections,
    ),
    _Spec(
        "grantr.revoke_connection",
        "Revoke one of your own connections at once: its next call is refused.",
        "grantr:revoke_connection",
        _Connection,
        lambda g, a, t, by: _entry(g.connections().revoke(t, a.connection, by=by, own_only=True)),
        reversibility="irreversible",
        route=f"{ADMIN}/access/connections",
    ),
    _Spec(
        "grantr.revoke_member_connection",
        "Revoke another member's connection at once, if you add the tenant's members: its next "
        "call is refused. It asks your confirmation.",
        "grantr:revoke_connection",
        _Connection,
        lambda g, a, t, by: _entry(g.connections().revoke(t, a.connection, by=by)),
        reversibility="irreversible",
        admin_high=True,
        route=f"{ADMIN}/access/connections",
    ),
    _read(
        "grantr.list_integrations",
        "List each integration as it is set on the tenant, or in one of its workspaces.",
        "grantr:manage_integrations",
        f"{ADMIN}/integrations",
        lambda g, a, t, by: _listed(g.integrations(t, workspace=a.workspace, by=by)),
        arguments=_InWorkspace,
    ),
    _Spec(
        "grantr.set_integration",
        "Turn an integration on or off on the tenant or in a workspace, or unset it.",
        "grantr:manage_integrations",
        _Integration,
        lambda g, a, t, by: _one(g.set_integration(t, a.key, a.on, workspace=a.workspace, by=by)),
        route=f"{ADMIN}/integrations",
    ),
    _read(
        "grantr.list_settings",
        "List each setting as it applies on the tenant, or in one of its workspaces.",
        "grantr:manage_settings",
        f"{ADMIN}/settings",
        lambda g, a, t, by: _one(g.settings(t, workspace=a.workspace, by=by)),
        arguments=_InWorkspace,
    ),
    _Spec(
        "grantr.set_setting",
        "Narrow a setting on the tenant or in a workspace, within the layer above, or unset it.",
        "grantr:manage_settings",
        _Setting,
        lambda g, a, t, by: _one(
            g.set_setting(t, a.key, a.value, version=a.version, workspace=a.workspace, by=by)
        ),
        route=f"{ADMIN}/settings",
    ),
    _read(
        "grantr.list_bindings",
        "List the sources bound to the tenant's workspaces, or one of them: the operator's first.",
        "grantr:manage_bindings",
        None,
        lambda g, a, t, by: _listed(g.bindings().listed(t, by=by, workspace=a.workspace)),
        arguments=_InWorkspace,
    ),
    _Spec(
        "grantr.bind",
        "Bind a source's connection to one of the tenant's workspaces, so its events reach it.",
        "grantr:manage_bindings",
        _Bind,
        lambda g, a, t, by: _entry(
            g.bindings().bind(
                t,
                a.workspace,
                a.source,
                a.connection,
                select=a.select,
                types=a.types,
                trust=a.trust,
                options=a.options,
                by=by,
            )
        ),
        route=None,
    ),
    _Spec(
        "grantr.unbind",
        "Remove one of the tenant's bindings, so its source's events stop reaching it.",
        "grantr:manage_bindings",
        _Binding,
        lambda g, a, t, by: _entry(g.bindings().unbind(t, a.binding, by=by)),
        route=None,
    ),
    _read(
        "grantr.read_audit",
        "Read the newest entries of the tenant's audit log of changes to access, oldest first.",
        "grantr:read_audit",
        f"{ADMIN}/audit",
        lambda g, a, t, by: _listed(
            g.audit(t, by=by, last=a.last, keep=AuditFilter(types=frozenset(a.types)))
        ),
        arguments=_Audit,
    ),
    _read(
        "grantr.list_approvals",
        "List the approvals pending in the tenant, or a workspace, that you may answer.",
        "grantr:read_approvals",
        f"{ADMIN}/approvals",
        _list_approvals,
        arguments=_InWorkspace,
        toolset="core",
    ),
    _read(
        "grantr.read_approval",
        "Read an approval as it stands: what it asks, who may answer, and its answer if any.",
        "grantr:read_approvals",
        f"{ADMIN}/approvals",
        _read_approval,
        arguments=_Approval,
        toolset="core",
    ),
    _Spec(
        "grantr.answer_approval",
        "Answer an approval.",
        "grantr:answer_approval",
        _Answer,
        _refused,
        toolset="core",
        exposure=NotExposed(reason="approvals come from a person: elicitation or portalr"),
        route=f"{ADMIN}/approvals",
        surfaces=frozenset({"portalr"}),
    ),
    _Spec(
        "grantr.delete_tenant",
        "Delete the tenant and everything grantr holds of it. It asks your confirmation.",
        "grantr:delete_tenant",
        _Nothing,
        lambda g, _a, t, by: _entry(g.delete_tenant(t, by=by)),
        reversibility="irreversible",
        admin_high=True,
        route=ADMIN,
    ),
    _Spec(
        "grantr.grant_operator",
        "Make a user one of the deployment's operators. It asks your confirmation.",
        "grantr:grant_operator",
        _Operator,
        lambda g, a, _t, by: _entry(g.grant_operator(a.user, by=by)),
        admin_high=True,
        route="/portalr/admin/deployment",
    ),
    _Spec(
        "grantr.revoke_operator",
        "Take the operator role from a user.",
        "grantr:grant_operator",
        _Operator,
        lambda g, a, _t, by: _entry(g.revoke_operator(a.user, by=by)),
        route="/portalr/admin/deployment",
    ),
)


def _schema(arguments: type[_Arguments]) -> JsonObject:
    schema: JsonObject = arguments.model_json_schema()
    del schema["title"]
    return schema


def _command(spec: _Spec) -> Command:
    capability = Capability.model_validate(
        {
            "name": spec.name,
            "version": VERSION,
            "description": spec.description,
            "input_schema": _schema(spec.arguments),
            "output_schema": None,
            "provider": "command",
            "tier": spec.tier,
            "effects": spec.effects,
            "reversibility": spec.reversibility,
            "gate": Gate(integration=None, action=spec.action),
            "risk_class": "admin_high" if spec.admin_high else None,
        }
    )
    return Command(
        capability=capability,
        toolset=spec.toolset,
        exposure=spec.exposure,
        route=spec.route,
        surfaces=spec.surfaces,
        # Access is the tenant's: a command names any workspace it acts on in its arguments.
        tenant_wide=True,
    )


_BY_NAME: Final = {spec.name: spec for spec in _SPECS}

ADMIN_HIGH: Final = frozenset(spec.name for spec in _SPECS if spec.admin_high)
"""The commands whose risk class is ``admin_high``: each asks its caller's own confirmation."""


class GrantrCommands:
    """grantr's static catalog: lattice-core's ``Commands``, with no I/O and no scope."""

    def __init__(self) -> None:
        self._commands = tuple(_command(spec) for spec in _SPECS)

    def commands(self) -> tuple[Command, ...]:
        """Return grantr's commands, in the order :data:`_SPECS` declares them."""
        return self._commands


CATALOG: Final = GrantrCommands()
"""grantr's catalog: what its ``lattice.commands`` entry point names, unbound."""


class GrantrProvider(GrantrCommands):
    """grantr's catalog bound to its grants: lattice-core's ``Provider`` and ``Commands``.

    Each call runs as the subject the call is for, in its tenant, so grantr checks it again.

    Args:
        grants: The application's grants.
    """

    def __init__(self, grants: Grants) -> None:
        super().__init__()
        self.kind: ProviderKind = "command"
        self._grants = grants
        self._offered = tuple(
            command.capability
            for command in self._commands
            if not isinstance(command.exposure, NotExposed)
        )

    def capabilities(self, _scope: Scope, /) -> tuple[Capability, ...]:
        """Return the capabilities a caller may call, the same in every workspace.

        The commands not exposed, answering an approval and issuing a key, aren't among them.
        """
        return self._offered

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """Run a command as the call's subject, in the call's tenant, and answer JSON text.

        Raises:
            ValueError: If the capability isn't one of grantr's offered commands.
            pydantic.ValidationError: If the arguments aren't the command's.
            grantr.core.Forbidden: If grantr refuses the subject.
            grantr.core.Invalid: If grantr refuses the command.
        """
        spec = _BY_NAME.get(capability.name)
        if spec is None:
            raise ValueError(f"{capability.name} isn't one of grantr's commands")
        given = spec.arguments.model_validate(arguments)
        answer = await spec.handler(
            self._grants, given, context.scope.tenant_id, subject_of_call(context)
        )
        return ToolResult(output=json.dumps(answer, sort_keys=True))


def provider(grants: Grants) -> GrantrProvider:
    """Bind grantr's catalog to the application's grants, at its composition root."""
    return GrantrProvider(grants)
