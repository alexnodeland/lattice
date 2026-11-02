"""portalr's commands: what a person reads and does in portalr's admin, declared once.

:data:`CATALOG` is portalr's static catalog, lattice-core's ``Commands`` (lattice RFC-0014,
portalr ADR-0094): a tenant's telemetry (traces, logs, metrics, scores, feedback, adoption), its
spend and usage, the deployment's tenants and links, creating a tenant and inviting a member, each
a ``command`` capability named ``portalr.<name>``, in the ``admin`` toolset. It reads no tool and
opens nothing, so the parity test, the schema and the docs read it as it is; an application binds
it at its composition root, as portr does (lattice ADR-0041).

- **A read's arguments are its route's query,** the readers' own models, so a client asks what
  portalr's admin asks.
- **Creating a tenant and inviting a member** are gated by grantr's actions, which portalr's routes
  ask before Supabase emails anyone: ``grantr:create_tenant``, which RFC-0014 makes portalr's
  command, and ``grantr:add_member``. Each sends an email out, which taint reads.
- **No command, by action** (:data:`LISTED`): none. A person's own analytics consent and session,
  the names of people and the models a turn may use are portalr's UI's own, gated by no action.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Any, Final

from pydantic import BaseModel, ConfigDict, StringConstraints

from lattice_core.capabilities import Capability, Effect, Gate, JsonObject, Reversibility, Tier
from lattice_core.commands import Command
from portalr.actions import READ_DEPLOYMENT, READ_SPEND, READ_TELEMETRY
from portalr.readers.analytics import AdoptionQuery
from portalr.readers.feedback import FeedbackQuery
from portalr.readers.loki import LogQuery
from portalr.readers.prometheus import MetricQuery
from portalr.readers.query import Window
from portalr.readers.tempo import TraceQuery
from portalr.readers.usage import UsageQuery

__all__ = [
    "ADD_MEMBER",
    "ARGUMENTS",
    "CATALOG",
    "CREATE_TENANT",
    "LISTED",
    "VERSION",
    "PortalrCommands",
]

VERSION: Final = "1.0.0"
"""Each command's version."""

ADMIN = "/portalr/admin/t/{tenant}"
"""A tenant in portalr's admin: where a tenant's command's route starts."""

DEPLOYMENT = "/portalr/admin/deployment"
"""The deployment in portalr's admin, for operators."""

CREATE_TENANT: Final = "grantr:create_tenant"
"""What creating a tenant asks, across the deployment: grantr's action, portalr's command."""

ADD_MEMBER: Final = "grantr:add_member"
"""What inviting a member asks, in the tenant."""

LISTED: Final = MappingProxyType[str, str]({})
"""Each of portalr's actions that is no command's gate, and why: none."""

Email = Annotated[str, StringConstraints(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=254)]
"""An email address, as portalr's routes take one."""


class _Arguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, use_attribute_docstrings=True)


class _Nothing(_Arguments):
    pass


class _Trace(_Arguments):
    trace_id: str
    """The trace."""


class _LogLine(_Arguments):
    record_id: str
    """The log record, as a list of logs gives its id."""


class _Links(_Arguments):
    trace_id: str | None = None
    """A trace to link to, in Langfuse."""
    session_id: str | None = None
    """A session to link to, in Langfuse."""
    run_id: str | None = None
    """A run to link to."""
    tenant_id: str | None = None
    """A tenant whose traces to link to."""


class _NewTenant(_Arguments):
    tenant: str
    """The new tenant's id."""
    owner_email: Email
    """Its first owner's email, whom Supabase invites."""


class _Invite(_Arguments):
    email: Email
    """Whom to invite: Supabase finds or invites them, and grantr adds them as a member."""


@dataclass(frozen=True)
class _Spec:
    name: str
    description: str
    action: str
    arguments: type[BaseModel]
    route: str
    tier: Tier = "read"
    reversibility: Reversibility = "none"
    effects: frozenset[Effect] = frozenset({"reads_private"})


def _write(
    name: str, description: str, action: str, arguments: type[BaseModel], route: str
) -> _Spec:
    return _Spec(
        name,
        description,
        action,
        arguments,
        route,
        tier="write",
        reversibility="compensable",
        effects=frozenset({"sends_out"}),
    )


_SPECS: Final[tuple[_Spec, ...]] = (
    _Spec(
        "portalr.list_traces",
        "List the tenant's traces in a window, newest first, optionally of one kind of span.",
        READ_TELEMETRY,
        TraceQuery,
        f"{ADMIN}/traces",
    ),
    _Spec(
        "portalr.read_trace",
        "Read one of the tenant's traces, with its spans.",
        READ_TELEMETRY,
        _Trace,
        f"{ADMIN}/traces/{{trace_id}}",
    ),
    _Spec(
        "portalr.read_logs",
        "Read the tenant's log records in a window, newest first, optionally filtered.",
        READ_TELEMETRY,
        LogQuery,
        f"{ADMIN}/logs",
    ),
    _Spec(
        "portalr.read_log_line",
        "Read one of the tenant's log records, with its fields.",
        READ_TELEMETRY,
        _LogLine,
        f"{ADMIN}/logs",
    ),
    _Spec(
        "portalr.read_metrics",
        "Read one of the tenant's metrics over a window.",
        READ_TELEMETRY,
        MetricQuery,
        ADMIN,
    ),
    _Spec(
        "portalr.read_scores",
        "Read the tenant's evaluation scores over a window.",
        READ_TELEMETRY,
        Window,
        f"{ADMIN}/feedback",
    ),
    _Spec(
        "portalr.read_feedback",
        "Read the feedback people and evaluators gave in the tenant over a span of time.",
        READ_TELEMETRY,
        FeedbackQuery,
        f"{ADMIN}/feedback",
    ),
    _Spec(
        "portalr.read_adoption",
        "Read how much the tenant's people use the portal over a span of time.",
        READ_TELEMETRY,
        AdoptionQuery,
        f"{ADMIN}/adoption",
    ),
    _Spec(
        "portalr.read_spend",
        "Read the tenant's spend on models against its budget.",
        READ_SPEND,
        _Nothing,
        f"{ADMIN}/usage",
    ),
    _Spec(
        "portalr.read_usage",
        "Read the tenant's use of models over a span of time, by model, person or workspace.",
        READ_SPEND,
        UsageQuery,
        f"{ADMIN}/usage",
    ),
    _Spec(
        "portalr.list_deployment_tenants",
        "List every tenant of the deployment, with its spend, for operators.",
        READ_DEPLOYMENT,
        _Nothing,
        f"{DEPLOYMENT}/tenants",
    ),
    _Spec(
        "portalr.deployment_links",
        "Make links into the deployment's own tools (Langfuse, Grafana, Umami) for a trace, a "
        "session, a run or a tenant, for operators. Each link made is recorded.",
        READ_DEPLOYMENT,
        _Links,
        f"{DEPLOYMENT}/tools",
    ),
    _write(
        "portalr.create_tenant",
        "Create a tenant, and invite its first owner by email, for operators.",
        CREATE_TENANT,
        _NewTenant,
        f"{DEPLOYMENT}/tenants",
    ),
    _write(
        "portalr.invite_member",
        "Invite someone to the tenant by email, as a member; inviting a member again changes "
        "nothing.",
        ADD_MEMBER,
        _Invite,
        f"{ADMIN}/access/members",
    ),
)


def _schema(arguments: type[BaseModel]) -> JsonObject:
    schema: dict[str, Any] = arguments.model_json_schema()
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
        }
    )
    # Admin's reads and changes are the tenant's or the deployment's, in no workspace.
    return Command(
        capability=capability, toolset="admin", exposure="tool", route=spec.route, tenant_wide=True
    )


class PortalrCommands:
    """portalr's static catalog: lattice-core's ``Commands``, with no I/O and no scope."""

    def __init__(self) -> None:
        self._commands = tuple(_command(spec) for spec in _SPECS)

    def commands(self) -> Iterable[Command]:
        """Return portalr's commands, in the order they are declared."""
        return self._commands


CATALOG: Final = PortalrCommands()
"""portalr's catalog, unbound: what an application binds at its composition root."""

ARGUMENTS: Final[Mapping[str, type[BaseModel]]] = MappingProxyType(
    {spec.name: spec.arguments for spec in _SPECS}
)
"""Each command's arguments, by its name: the model a bound provider validates a call with."""
