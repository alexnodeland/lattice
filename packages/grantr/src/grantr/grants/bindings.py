"""grantr's bindings: lattice-core's ``Bindings``, and the commands that change them.

A binding says which of a source's events reach which workspace (lattice ADR-0040). There are
two layers, as settings have: the operator's, given in the deployment's configuration and read
only, and each tenant's, in its own rows, under row-level security. A tenant's owners and admins
bind and unbind its sources with ``grantr:manage_bindings``, each change in the tenant's audit
log in its transaction (grantr ADR-0041).

As the port, :meth:`GrantrBindings.for_connection` answers the deployment's intake: the
operator's bindings of the connection, and every tenant's, read tenant by tenant, as the sweep
of approvals reads them. :meth:`GrantrBindings.for_workspace` answers one workspace's.
"""

import secrets
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Final

from grantr.core import (
    TENANT,
    AuditEntry,
    BindingAdded,
    BindingRemoved,
    Invalid,
    Resource,
    RulePrincipal,
    ServicePrincipal,
    Subject,
    TenantId,
    User,
    WorkspaceId,
)
from grantr.core.ids import TENANT_ID
from grantr.core.roles import MANAGE_BINDINGS
from grantr.grants.calls import Change
from grantr.grants.storage import Reads, Storage
from lattice_core.bindings import SOURCE, Binding, BindingId, Trust
from lattice_core.capabilities import JsonObject

type Require = Callable[[Reads, TenantId, Subject, str, Resource], Awaitable[None]]
"""Refuses a subject that doesn't hold an action on a resource, from :class:`Grants`."""

OPERATOR: Final = "operator"
"""Who made the operator's bindings, as a binding's ``by`` names them."""


def _who(subject: Subject) -> str:
    """Who bound a binding, as its ``by`` names them: ``user:alice``."""
    match subject:
        case User() | ServicePrincipal():
            return f"{subject.kind}:{subject.id}"
        case RulePrincipal():
            return f"rule:{subject.workspace}/{subject.rule}"
        case _:
            return subject.kind


def _check(
    tenant: TenantId,
    workspace: WorkspaceId,
    source: str,
    connection: str,
    types: frozenset[str] | None,
) -> None:
    """Refuse a binding that isn't well formed, before it is made.

    Raises:
        Invalid: Saying how.
    """
    if not TENANT_ID.fullmatch(tenant):
        raise Invalid("a tenant's id isn't empty, and has no ~")
    if not SOURCE.fullmatch(source):
        raise Invalid(f"a source's name is lowercase and hyphens, not {source!r}")
    if not workspace or not connection:
        raise Invalid("a binding names a workspace and a connection")
    if types is not None and not types:
        raise Invalid("a binding receives some types, or every one with types=None")


class GrantrBindings:
    """lattice-core's ``Bindings`` over grantr's storage, and the commands that change them.

    What :meth:`Grants.bindings` returns.

    Args:
        storage: grantr's storage.
        change: A change to one tenant, from :class:`~grantr.grants.Grants`.
        require: Refuses a subject that doesn't hold an action, from
            :class:`~grantr.grants.Grants`.
        operator: The operator's bindings, from the deployment's configuration.

    Raises:
        ValueError: If two of the operator's bindings share an id.
    """

    def __init__(
        self,
        storage: Storage,
        *,
        change: Change,
        require: Require,
        operator: Iterable[Binding] = (),
    ) -> None:
        self._storage = storage
        self._change = change
        self._require = require
        self._operator: dict[BindingId, Binding] = {}
        for binding in operator:
            if binding.id in self._operator:
                raise ValueError(f"the operator binds {binding.id} twice")
            self._operator[binding.id] = binding

    async def bind(
        self,
        tenant: TenantId,
        workspace: WorkspaceId,
        source: str,
        connection: str,
        *,
        select: JsonObject | None = None,
        types: Iterable[str] | None = None,
        trust: Trust | None = None,
        options: JsonObject | None = None,
        by: Subject,
    ) -> AuditEntry:
        """Bind a source's connection to one of the tenant's workspaces, and return the entry.

        Raises:
            Invalid: If the binding isn't well formed: a source's name, an empty workspace or
                connection, or no types at all.
            Forbidden: If ``by`` doesn't hold ``grantr:manage_bindings`` on the tenant.
        """
        received = None if types is None else frozenset(types)
        _check(tenant, workspace, source, connection, received)
        binding = Binding(
            id=f"bnd_{secrets.token_hex(8)}",
            tenant_id=tenant,
            workspace_id=workspace,
            source=source,
            connection=connection,
            select=select or {},
            types=received,
            trust=trust,
            options=options or {},
            bound_at=datetime.now(UTC),
            by=_who(by),
        )
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, MANAGE_BINDINGS, TENANT)
            event = BindingAdded(
                binding=binding.id,
                workspace=workspace,
                source=source,
                connection=connection,
                types=None if binding.types is None else sorted(binding.types),
                trust=trust,
            )
            entry = await record(tenant, by, event)
            await tx.put_binding(binding.model_copy(update={"bound_at": entry.at}))
            return entry

    async def unbind(self, tenant: TenantId, id: BindingId, /, *, by: Subject) -> AuditEntry:
        """Remove one of the tenant's bindings, and return the entry.

        Raises:
            Invalid: If it is the operator's, set in the deployment's configuration, or the
                tenant has no binding of the id.
            Forbidden: If ``by`` doesn't hold ``grantr:manage_bindings`` on the tenant.
        """
        if id in self._operator:
            raise Invalid(f"{id} is the operator's, set in the deployment's configuration")
        async with self._change(tenant) as (tx, record):
            await self._require(tx, tenant, by, MANAGE_BINDINGS, TENANT)
            gone = await tx.delete_binding(tenant, id)
            if gone is None:
                raise Invalid(f"there is no binding {id}")
            event = BindingRemoved(
                binding=id,
                workspace=gone.workspace_id,
                source=gone.source,
                connection=gone.connection,
            )
            return await record(tenant, by, event)

    async def listed(
        self, tenant: TenantId, *, by: Subject, workspace: WorkspaceId | None = None
    ) -> list[Binding]:
        """The bindings that reach the tenant's workspaces, or one of them.

        The operator's come first, then the tenant's, each oldest first.

        Raises:
            Forbidden: If ``by`` doesn't hold ``grantr:manage_bindings`` on the tenant.
        """
        await self._require(self._storage, tenant, by, MANAGE_BINDINGS, TENANT)
        stored = await self._storage.bindings(tenant, workspace=workspace)
        operator = [
            binding
            for binding in self._operator.values()
            if binding.tenant_id == tenant and workspace in (None, binding.workspace_id)
        ]
        return operator + stored

    async def for_connection(self, source: str, connection: str, /) -> list[Binding]:
        """Every binding of the source's connection: the operator's, then each tenant's.

        It is what the deployment's intake routes an occurrence by, reading each tenant in turn.
        """
        found = [
            binding
            for binding in self._operator.values()
            if (binding.source, binding.connection) == (source, connection)
        ]
        for tenant in await self._storage.tenants():
            found += await self._storage.bindings(tenant, source=source, connection=connection)
        return found

    async def for_workspace(self, tenant_id: str, workspace_id: str, /) -> list[Binding]:
        """Every binding that reaches the tenant's workspace: the operator's, then the tenant's.

        An id no tenant can have has none.
        """
        if not TENANT_ID.fullmatch(tenant_id):
            return []
        operator = [
            binding
            for binding in self._operator.values()
            if (binding.tenant_id, binding.workspace_id) == (tenant_id, workspace_id)
        ]
        return operator + await self._storage.bindings(tenant_id, workspace=workspace_id)
