"""Capabilities: every tool an agent can call, offered by providers through one registry.

A :class:`Capability` is a tool, declared once by the package that provides it: its name, its
own version, what it does, its input's and output's JSON Schemas, the kind of provider that
offers it, its capability tier (``read``, ``write``, ``run_code`` or ``outbound``), its effects
(what taint reads), whether it can be undone, the integration and grantr action that gate it,
and the settings that limit it. Each package's :class:`Provider` offers its capabilities per
:class:`Scope`, a tenant's workspace, and calls them with a :class:`CallContext`: who called,
the call's taint, its correlation id, the surface it came from, and the outside client it came
through, if any (lattice RFC-0011).

A :class:`Registry` composes the providers an application passes it, as
``Registry(*providers)``: it lists a scope's capabilities, refuses two of one name, finds one by
name and searches them by text. A library names its provider in its ``pyproject.toml``, in the
entry-point group :data:`GROUP`, and :func:`discover` loads every one installed; an application
may pass its providers by hand instead, and tests always do.

The registry only composes: it gates nothing and calls nothing. Every call goes through the
enforcement path, which checks the gate, the tier, the limits, taint and approval in order, and
is not declared here yet. :class:`FakeProvider` is a provider for tests.

The contract's version is :data:`CONTRACT`, and its JSON Schema, which :func:`contract_schema`
returns, is checked in at ``schemas/capabilities.v1.json``: regenerate it with ``moon run
lattice-core:schema`` (:mod:`lattice_core.contracts`).
"""

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Annotated, Final, Literal, Protocol, Self, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from lattice_core.integrations import KEY
from lattice_core.schema import tag_required
from lattice_core.taint import Taint

__all__ = [
    "ACTION",
    "CONTRACT",
    "EFFECTS",
    "GROUP",
    "NAME",
    "PROVIDER_KINDS",
    "TIERS",
    "VERSION",
    "CallContext",
    "Caller",
    "Capability",
    "ClientSurface",
    "DuplicateCapability",
    "Effect",
    "FakeCall",
    "FakeProvider",
    "Gate",
    "JsonObject",
    "PersonCaller",
    "Provider",
    "ProviderKind",
    "Registered",
    "Registry",
    "Reversibility",
    "RiskClass",
    "RunCaller",
    "Scope",
    "SessionCaller",
    "Tier",
    "ToolResult",
    "Via",
    "contract_schema",
    "discover",
]

CONTRACT: Final = "1.1.0"
"""The contract's version. A removed field or a changed meaning is a major version; an optional
field, a new :data:`Effect` or a new :data:`ProviderKind` is a minor one, and a consumer treats
a value it doesn't know as the strictest."""

GROUP: Final = "lattice.capabilities"
"""The entry-point group a library names its provider in, for :func:`discover`."""

Tier = Literal["read", "write", "run_code", "outbound"]
"""A capability's tier, which decides who may be offered it: it reads, it writes, it runs code,
or it reaches outside the deployment. Not the settings' :data:`lattice_core.settings.Tier`."""

TIERS: Final[tuple[Tier, ...]] = ("read", "write", "run_code", "outbound")
"""The capability tiers, from the least to the most a capability may do."""

Effect = Literal["reads_private", "reads_untrusted", "sends_out"]
"""What a call does that taint reads: it reads private data, it reads untrusted content (which
taints the caller), or it sends data out."""

EFFECTS: Final[tuple[Effect, ...]] = ("reads_private", "reads_untrusted", "sends_out")
"""The effects a capability may declare."""

Reversibility = Literal["none", "undoable", "compensable", "irreversible"]
"""Whether a call can be undone: it changes nothing, it can be undone, a later call can make up
for it, or it can't be undone."""

ProviderKind = Literal[
    "command", "connector_action", "mcp_tool", "code_session", "workflow", "builtin"
]
"""The kind of provider that offers a capability: a lattice command, a connector's action, an
MCP server's tool, a code session's tool, a stored workflow, or a built-in such as web search."""

PROVIDER_KINDS: Final[tuple[ProviderKind, ...]] = (
    "command",
    "connector_action",
    "mcp_tool",
    "code_session",
    "workflow",
    "builtin",
)
"""The kinds of provider."""

RiskClass = Literal["admin_high"]
"""A risk class beyond the tier: ``admin_high`` asks the caller's own fresh confirmation."""

ClientSurface = Literal["mcp", "acp"]
"""The protocol an outside client calls through."""

type JsonObject = dict[str, JsonValue]
"""A JSON object: a call's arguments, or a JSON Schema."""

NAME: Final = re.compile(r"[a-z][a-z0-9_-]*(\.[A-Za-z0-9_-]+)+")
"""A capability name's form: its provider, a dot and its tool, such as ``artifactr.edit_text``.
The tool may itself be dotted, such as ``mcp.github.create_issue``."""

VERSION: Final = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?"
)
"""A semantic version: ``MAJOR.MINOR.PATCH``, with an optional pre-release and build."""

ACTION: Final = re.compile(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*")
"""A grantr action's form: a package, a colon and an action, such as
``artifactr:edit_artifact``."""


class Gate(BaseModel):
    """What gates a capability: the integration it needs on, and the grantr action it needs.

    Raises:
        ValueError: If ``integration`` isn't an integration key, or ``action`` isn't of
            :data:`ACTION`'s form.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    integration: str | None
    """An integration's key (lattice ADR-0027), or None for a capability always installed."""
    action: str
    """The grantr action the caller must hold, such as ``artifactr:edit_artifact``."""
    different_approver: bool = False
    """Whether an approval of a call must come from someone other than the caller."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if self.integration is not None and not KEY.fullmatch(self.integration):
            raise ValueError(f"not an integration key: {self.integration!r}")
        if not ACTION.fullmatch(self.action):
            raise ValueError(f"a grantr action is package:action, not {self.action!r}")
        return self


class Capability(BaseModel):
    """A tool an agent can call, as its provider declares it.

    Raises:
        ValueError: If the name isn't of :data:`NAME`'s form, the version isn't of
            :data:`VERSION`'s, the description is empty, or a limit isn't a setting's key.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    name: str
    """Its provider, a dot and its tool: ``artifactr.edit_text``, ``mcp.github.create_issue``."""
    version: str
    """The tool's own semantic version: a new input field is a minor version."""
    description: str
    """What it does, for the agent that picks it and the person who approves it."""
    input_schema: JsonObject
    """The JSON Schema of its arguments."""
    output_schema: JsonObject | None
    """The JSON Schema of its output, or None if it declares none."""
    provider: ProviderKind
    """The kind of provider that offers it."""
    tier: Tier
    """Its capability tier."""
    effects: frozenset[Effect]
    """What a call does that taint reads."""
    reversibility: Reversibility
    """Whether a call can be undone."""
    gate: Gate
    """The integration and the grantr action that gate it."""
    limits: tuple[str, ...] = ()
    """The keys of the settings that limit it (lattice ADR-0030), such as
    ``calls-per-hour:mcp-github``."""
    risk_class: RiskClass | None = None
    """A risk class beyond its tier, if it has one."""

    @model_validator(mode="after")
    def _well_formed(self) -> Self:
        if not NAME.fullmatch(self.name):
            raise ValueError(f"a capability's name is provider.tool, not {self.name!r}")
        if not VERSION.fullmatch(self.version):
            raise ValueError(f"{self.name}'s version is MAJOR.MINOR.PATCH, not {self.version!r}")
        if not self.description.strip():
            raise ValueError(f"{self.name} needs a description")
        if malformed := [key for key in self.limits if not KEY.fullmatch(key)]:
            raise ValueError(f"{self.name}'s limits aren't settings' keys: {malformed}")
        return self


class Scope(BaseModel):
    """Where capabilities are offered and called: a tenant's workspace, or the tenant as a whole.

    A tenant-wide command, such as listing a tenant's workspaces, is called with no workspace
    (lattice ADR-0044); everything else is called in one.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    tenant_id: str
    workspace_id: str | None = None
    """The workspace, or None for the tenant as a whole."""


class PersonCaller(BaseModel):
    """A person calling for themselves, by their identity provider's id."""

    model_config = ConfigDict(
        frozen=True, use_attribute_docstrings=True, json_schema_extra=tag_required
    )

    kind: Literal["person"] = "person"
    id: str


class RunCaller(BaseModel):
    """An agent's run, or a stored workflow's, calling as part of its work."""

    model_config = ConfigDict(
        frozen=True, use_attribute_docstrings=True, json_schema_extra=tag_required
    )

    kind: Literal["run"] = "run"
    id: str
    """The run's id."""
    agent: str
    """The agent or stored workflow the run runs, whose tier ceiling applies."""
    on_behalf_of: str | None = None
    """The id of the person the run acts for, if it acts for one."""


class SessionCaller(BaseModel):
    """A code session calling as part of its work."""

    model_config = ConfigDict(
        frozen=True, use_attribute_docstrings=True, json_schema_extra=tag_required
    )

    kind: Literal["session"] = "session"
    id: str
    """The session's id."""
    on_behalf_of: str | None = None
    """The id of the person the session acts for, if it acts for one."""


type Caller = Annotated[PersonCaller | RunCaller | SessionCaller, Field(discriminator="kind")]
"""Who calls a capability, discriminated by ``kind``: a person, an agent's run or a code
session."""


class Via(BaseModel):
    """The outside client a call came through (lattice RFC-0014).

    A provider builds its actor from it, the client acting for the caller, so grants are the
    caller's own and audit names the client.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    connection_id: str
    """The id of the connection the client called through."""
    client_name: str
    """The client's name, as audit shows it: "Alex via Claude"."""
    surface: ClientSurface
    """The protocol the client called through."""


class CallContext(BaseModel):
    """What a call carries besides its arguments: where, who, its taint and where it came from.

    The approvals and the egress policy read the same context.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    scope: Scope
    """The tenant's workspace the call is made in."""
    caller: Caller
    """Who calls."""
    taint: Taint
    """The caller's taint: its turn's, run's or session's."""
    correlation_id: str
    """The id that ties the call to the turn, run or session that made it, in logs and audit."""
    surface: str
    """The surface the call came from, such as ``portalr``, ``mcp`` or ``acp``."""
    via: Via | None = None
    """The outside client the call came through, or None for a call from lattice's own
    surfaces."""


class ToolResult(BaseModel):
    """What a call returned."""

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    output: JsonValue = None
    """The call's output, as JSON, of the capability's ``output_schema`` where it declares one."""


@runtime_checkable
class Provider(Protocol):
    """A package's capabilities, offered per scope, and called through the enforcement path.

    A provider whose capabilities are the same everywhere ignores the scope; one whose
    capabilities differ by tenant, such as a tenant's MCP servers, answers per scope. Its
    arguments are positional, so an implementation names them as it likes.
    """

    kind: ProviderKind
    """The kind of provider it is."""

    def capabilities(self, scope: Scope, /) -> Iterable[Capability]:
        """Return the capabilities it offers in the scope."""
        ...

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """Call one of its capabilities with the arguments, in the call's context."""
        ...


class DuplicateCapability(ValueError):
    """Two capabilities of one name in a scope.

    Args:
        name: The name offered twice.
        scope: The scope it was offered twice in.
    """

    def __init__(self, name: str, scope: Scope) -> None:
        super().__init__(
            f"{name} is offered twice in tenant {scope.tenant_id}'s workspace {scope.workspace_id}"
        )
        self.name = name
        self.scope = scope


@dataclass(frozen=True)
class Registered:
    """A capability, and the provider that offers it."""

    capability: Capability
    provider: Provider


class Registry:
    """The capabilities of every provider, composed: listed, found and searched per scope.

    Each lookup asks the providers again, since what a provider offers may change by scope and
    over time. A name offered twice in a scope is refused, whichever providers offer it.

    Args:
        *providers: The providers, in the order their capabilities are listed.
    """

    def __init__(self, *providers: Provider) -> None:
        self._providers = providers

    @property
    def providers(self) -> tuple[Provider, ...]:
        """The providers, in the order given."""
        return self._providers

    def _registered(self, scope: Scope) -> dict[str, Registered]:
        found: dict[str, Registered] = {}
        for provider in self._providers:
            for capability in provider.capabilities(scope):
                if capability.name in found:
                    raise DuplicateCapability(capability.name, scope)
                found[capability.name] = Registered(capability, provider)
        return found

    def capabilities(self, scope: Scope) -> tuple[Capability, ...]:
        """Return every capability offered in the scope, in the providers' order.

        Raises:
            DuplicateCapability: If two capabilities of one name are offered in it.
        """
        return tuple(registered.capability for registered in self._registered(scope).values())

    def find(self, scope: Scope, name: str) -> Registered | None:
        """Return the capability of the name offered in the scope, and its provider, if any.

        Raises:
            DuplicateCapability: If two capabilities of one name are offered in it.
        """
        return self._registered(scope).get(name)

    def search(self, scope: Scope, text: str) -> tuple[Capability, ...]:
        """Return the capabilities offered in the scope that the text describes.

        A capability matches when each word of the text, ignoring case, is in its name or its
        description. Text with no words matches every capability.

        Raises:
            DuplicateCapability: If two capabilities of one name are offered in it.
        """
        words = text.casefold().split()
        return tuple(
            capability
            for capability in self.capabilities(scope)
            if all(
                word in f"{capability.name} {capability.description}".casefold() for word in words
            )
        )


def discover(group: str = GROUP) -> tuple[Provider, ...]:
    """Return the providers installed packages name in the entry-point group, by their names.

    Args:
        group: The entry-point group; :data:`GROUP` if omitted.

    Raises:
        TypeError: If an entry point names something that isn't a :class:`Provider`.
    """
    providers: list[Provider] = []
    for entry_point in sorted(entry_points(group=group), key=lambda point: point.name):
        loaded: object = entry_point.load()
        if not isinstance(loaded, Provider):
            raise TypeError(f"{entry_point.name} = {entry_point.value!r} is not a provider")
        providers.append(loaded)
    return tuple(providers)


@dataclass(frozen=True)
class FakeCall:
    """A call a :class:`FakeProvider` received."""

    capability: Capability
    arguments: JsonObject
    context: CallContext


class FakeProvider:
    """A provider for tests: it offers the capabilities given, in every scope, and records calls.

    Args:
        kind: The kind of provider it stands for.
        *capabilities: The capabilities it offers.
        results: What a call of each capability, by name, returns, or raises if it is an
            exception. A capability not named returns an empty :class:`ToolResult`.
    """

    def __init__(
        self,
        kind: ProviderKind,
        *capabilities: Capability,
        results: Mapping[str, ToolResult | Exception] | None = None,
    ) -> None:
        self.kind: ProviderKind = kind
        self._capabilities = capabilities
        self._results: Mapping[str, ToolResult | Exception] = results or {}
        self.calls: list[FakeCall] = []
        """Every call it received, in order."""

    def capabilities(self, _scope: Scope, /) -> tuple[Capability, ...]:
        """Return the capabilities it was given, whatever the scope."""
        return self._capabilities

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        """Record the call, and return or raise what ``results`` names for the capability."""
        self.calls.append(FakeCall(capability, arguments, context))
        result = self._results.get(capability.name, ToolResult())
        if isinstance(result, Exception):
            raise result
        return result


class _Contract(BaseModel):
    capability: Capability
    context: CallContext
    result: ToolResult


def contract_schema() -> dict[str, JsonValue]:
    """Return the contract's JSON Schema: a capability, a call's context and a call's result."""
    schema = _Contract.model_json_schema()
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": f"lattice.capabilities {CONTRACT}",
        "description": (
            "lattice's capability contract: `capability` is a tool as its provider declares it, "
            "`context` what a call carries besides its arguments, and `result` what it returns."
        ),
        "type": "object",
        "properties": schema["properties"],
        "$defs": schema["$defs"],
    }
