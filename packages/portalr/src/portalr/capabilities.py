"""portalr's catalog bound to its readers and grantr: its provider, for a tenant's commands.

:class:`PortalrProvider` is lattice-core's ``Provider`` and ``Commands`` for portalr's commands a
client may call in a tenant (lattice RFC-0014, portalr ADR-0097): the tenant's telemetry, spend,
usage and adoption, and inviting a member. Each call is checked, as portalr's routes check it,
before a reader is asked: grantr's action on the tenant, as the person the call is for, and,
for an analytics session's traces, whether they operate the deployment (portalr ADR-0073). It
answers what the routes answer, as JSON.

The operators' commands, the deployment's tenants and links and creating a tenant, are checked
on the deployment, not on a tenant, so a call through the enforcer, which checks a tenant-wide
call on its tenant (lattice ADR-0044), can't reach them: it offers none of them, and they stay
portalr's admin's.
"""

import json
import re
from collections.abc import Callable
from typing import Final

from pydantic import BaseModel

from grantr.core import DEPLOYMENT, TENANT, Forbidden, Subject, User
from grantr.grants import Grants
from grantr.grants.calls import subject_of_call
from lattice_core.capabilities import (
    CallContext,
    Capability,
    JsonObject,
    ProviderKind,
    Scope,
    ToolResult,
)
from portalr.actions import READ_DEPLOYMENT
from portalr.commands import ARGUMENTS, PortalrCommands
from portalr.invites import Invite
from portalr.readers import (
    AdoptionQuery,
    FeedbackQuery,
    LogQuery,
    MetricQuery,
    Ok,
    Readers,
    TraceQuery,
    Unconfigured,
    UsageQuery,
    Window,
    read_feedback,
    read_usage,
)
from portalr.readers.loki import RECORD_ID
from portalr.readers.tempo import carries_analytics_session, for_tenant
from portalr.tenant import Tenant, allowed

__all__ = ["OPERATORS", "PortalrProvider"]

OPERATORS: Final = frozenset(
    {"portalr.list_deployment_tenants", "portalr.deployment_links", "portalr.create_tenant"}
)
"""The operators' commands, checked on the deployment: not offered through the enforcer."""

INVITE: Final = "portalr.invite_member"

_RECORD_ID: Final = re.compile(RECORD_ID)


class PortalrProvider(PortalrCommands):
    """portalr's catalog bound to its readers: lattice-core's ``Provider`` and ``Commands``.

    Args:
        grants: What decides each call, and adds invited members.
        readers: The stack's tools, each optional; a read of one not configured answers so.
        invite: Supabase Auth's admin API; without it, inviting a member isn't offered.
        subject_of: The subject a call is checked as; grantr's, the person it is for, if omitted.
    """

    def __init__(
        self,
        grants: Grants,
        readers: Readers,
        *,
        invite: Invite | None = None,
        subject_of: Callable[[CallContext], Subject] = subject_of_call,
    ) -> None:
        super().__init__()
        self.kind: ProviderKind = "command"
        self._grants = grants
        self._readers = readers
        self._invite = invite
        self._subject_of = subject_of
        self._offered = tuple(
            command.capability
            for command in self._commands
            if command.name not in OPERATORS and (command.name != INVITE or invite is not None)
        )
        self._names = frozenset(capability.name for capability in self._offered)

    def capabilities(self, _scope: Scope, /) -> tuple[Capability, ...]:
        """Return the tenant's commands a client may call, the same everywhere."""
        return self._offered

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """Read the tenant's telemetry, spend or adoption, or invite a member, and answer JSON.

        Raises:
            ValueError: If the capability isn't one this provider offers, or a log record's id
                isn't one.
            pydantic.ValidationError: If the arguments aren't the command's.
            grantr.core.Forbidden: If the caller doesn't hold the command's action on the
                tenant, or asks for an analytics session's traces and doesn't operate.
            portalr.invites.InviteFailed: If Supabase Auth didn't invite or find the person.
        """
        name = capability.name
        if name not in self._names:
            raise ValueError(f"{name} isn't a command this provider offers")
        given = ARGUMENTS[name].model_validate(arguments)
        tenant_id, subject = context.scope.tenant_id, self._subject_of(context)
        action = capability.gate.action
        if not await self._grants.check(tenant_id, subject, action, TENANT):
            raise Forbidden(f"the caller may not {action} in {tenant_id}")
        if name == INVITE:
            return ToolResult(output=await self._invited(tenant_id, subject, given))
        read = await self._read(allowed(tenant_id), subject, name, given)
        return ToolResult(output=read.model_dump_json())

    async def _read(
        self, tenant: Tenant, subject: Subject, name: str, given: BaseModel
    ) -> BaseModel:
        """A tenant's read, as portalr's route reads it."""
        readers = self._readers
        match given:
            case TraceQuery():
                if given.analytics_session is not None and not await self._operates(subject):
                    raise Forbidden("only operators find traces by analytics session")
                return (
                    await readers.tempo.search(tenant, given) if readers.tempo else Unconfigured()
                )
            case LogQuery():
                return await readers.loki.logs(tenant, given) if readers.loki else Unconfigured()
            case MetricQuery():
                if readers.prometheus is None:
                    return Unconfigured()
                return await readers.prometheus.series(tenant, given)
            case FeedbackQuery():
                if readers.langfuse is None:
                    return Unconfigured()
                return await read_feedback(readers.langfuse, tenant, given)
            case Window():
                return (
                    await readers.langfuse.scores(tenant, given)
                    if readers.langfuse
                    else Unconfigured()
                )
            case AdoptionQuery():
                if readers.analytics is None:
                    return Unconfigured()
                return await readers.analytics.adoption(tenant, given)
            case UsageQuery():
                if readers.litellm is None:
                    return Unconfigured()
                return await read_usage(readers.litellm, tenant, given)
            case _ if name == "portalr.read_spend":
                return await readers.litellm.spend(tenant) if readers.litellm else Unconfigured()
            case _ if name == "portalr.read_log_line":
                record_id = str(given.model_dump()["record_id"])
                if not _RECORD_ID.fullmatch(record_id):
                    raise ValueError(f"{record_id!r} isn't a log record's id")
                return (
                    await readers.loki.record(tenant, record_id) if readers.loki else Unconfigured()
                )
            case _:  # portalr.read_trace
                return await self._trace(tenant, subject, str(given.model_dump()["trace_id"]))

    async def _trace(self, tenant: Tenant, subject: Subject, trace_id: str) -> BaseModel:
        """A trace, its analytics session the operators' alone (portalr ADR-0073)."""
        if self._readers.tempo is None:
            return Unconfigured()
        read = await self._readers.tempo.trace(tenant, trace_id, reveal=None)
        if (
            isinstance(read, Ok)
            and read.data is not None
            and carries_analytics_session(read.data)
            and not await self._operates(subject)
        ):
            return Ok(data=for_tenant(read.data))
        return read

    async def _invited(self, tenant_id: str, subject: Subject, given: BaseModel) -> str:
        """Invite someone, and add them as a member if they aren't: inviting again does nothing."""
        assert self._invite is not None, "inviting a member is offered with an invite alone"
        user = await self._invite(str(given.model_dump()["email"]))
        if await self._grants.member(tenant_id, user) is None:
            await self._grants.add_member(tenant_id, User(id=user), by=subject)
        return json.dumps({"tenant": tenant_id, "user": user})

    async def _operates(self, subject: Subject) -> bool:
        return await self._grants.check("deployment", subject, READ_DEPLOYMENT, DEPLOYMENT)
