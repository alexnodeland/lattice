"""grantr's answers to lattice-core's enforcer: whether a caller holds a gate, and the call's audit.

The enforcer (lattice ADR-0037) asks ``Authorize`` whether a call's caller holds the capability's
grantr action in the call's workspace, and records every call through ``Audit``. grantr answers
both (grantr ADR-0039): a caller is checked as the person it is or acts for, and an agent's run or
a code session acting for no one as the agent, which holds nothing. Every call is a
``capability_called`` entry in its tenant's audit log, or, where the call names a tenant that
doesn't exist, in the deployment's, so a forged scope is seen by the operators.
"""

from collections.abc import Awaitable, Callable
from contextlib import AbstractAsyncContextManager

from grantr.core import (
    Agent,
    AuditEntry,
    AuditEvent,
    CapabilityCalled,
    CapabilityStep,
    Subject,
    TenantId,
    User,
)
from grantr.core.ids import TENANT_ID
from grantr.grants.storage import Reads, Transaction
from lattice_core.capabilities import CallContext, PersonCaller
from lattice_core.enforcement import CapabilityCalled as Called

type Record = Callable[[TenantId | None, Subject | None, AuditEvent], Awaitable[AuditEntry]]
"""Appends an audit entry in a change's transaction."""

type Change = Callable[[TenantId | None], AbstractAsyncContextManager[tuple[Transaction, Record]]]
"""A change to one tenant, or to the deployment with None."""


def subject_of_call(context: CallContext) -> Subject:
    """The subject a call is checked and audited as: the person it is or acts for, or the agent.

    A person calling, through lattice's surfaces or an outside client, is checked as themselves,
    as the client acts for them (lattice RFC-0014). An agent's run or a code session acting for a
    person is checked as that person; one acting for no one is the agent, which holds nothing.
    """
    caller = context.caller
    if isinstance(caller, PersonCaller):
        return User(id=caller.id)
    return Agent() if caller.on_behalf_of is None else User(id=caller.on_behalf_of)


def _event(entry: Called, *, claimed: str | None) -> CapabilityCalled:
    via = entry.via
    return CapabilityCalled(
        capability=entry.capability,
        version=entry.version,
        workspace=entry.scope.workspace_id,
        tenant=claimed,
        caller=entry.caller,
        client=None if via is None else f"{via.client_name} ({via.connection_id})",
        correlation_id=entry.correlation_id,
        surface=entry.surface,
        arguments_digest=entry.arguments_digest,
        steps=tuple(
            CapabilityStep(name=step.name, passed=step.passed, note=step.note)
            for step in entry.steps
        ),
        outcome=entry.outcome,
        approval=entry.approval,
        called_at=entry.at,
    )


class CallAudit:
    """lattice-core's ``Audit``, in grantr's log: what :meth:`Grants.capability_audit` returns.

    Each call is one ``capability_called`` entry in its tenant's log, made by the person the call
    is for, or by the agent where it is for no one. A call that names a tenant that doesn't exist,
    or an id no tenant can have, is recorded in the deployment's log instead, with the tenant it
    named, and never refused: the enforcer records every call, and its record must not fail the
    call.

    Args:
        reads: grantr's storage, to find whether the tenant exists.
        change: A change to a tenant or to the deployment, from :class:`~grantr.grants.Grants`.
    """

    def __init__(self, reads: Reads, *, change: Change) -> None:
        self._reads = reads
        self._change = change

    async def record(self, entry: Called, /) -> None:
        """Record the call in its tenant's audit log, or the deployment's."""
        tenant = entry.scope.tenant_id
        known = bool(TENANT_ID.fullmatch(tenant)) and await self._reads.tenant(tenant)
        by = _maker(entry)
        async with self._change(tenant if known else None) as (_, record):
            await record(
                tenant if known else None, by, _event(entry, claimed=None if known else tenant)
            )


def _maker(entry: Called) -> Subject:
    """Who made a call, as the audit records it: the person it was for, or the agent."""
    return Agent() if entry.on_behalf_of is None else User(id=entry.on_behalf_of)
