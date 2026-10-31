"""The capability registry: capabilities declared, composed per scope, found, searched and
discovered through entry points."""

import sys
import types
from collections.abc import Iterable
from datetime import UTC, datetime
from importlib.metadata import EntryPoint
from typing import Any

import pytest
from pydantic import ValidationError

from lattice_core import capabilities
from lattice_core.capabilities import (
    EFFECTS,
    GROUP,
    PROVIDER_KINDS,
    TIERS,
    CallContext,
    Capability,
    DuplicateCapability,
    FakeCall,
    FakeProvider,
    Gate,
    JsonObject,
    PersonCaller,
    Provider,
    ProviderKind,
    Registered,
    Registry,
    RunCaller,
    Scope,
    SessionCaller,
    ToolResult,
    Via,
    discover,
)
from lattice_core.taint import Cause, Clean, Tainted

HERE = Scope(tenant_id="acme", workspace_id="docs")
THERE = Scope(tenant_id="acme", workspace_id="ops")


def capability(name: str = "artifactr.edit_text", **changes: Any) -> Capability:
    """A capability of the name, with any fields changed."""
    fields: dict[str, Any] = {
        "name": name,
        "version": "1.0.0",
        "description": "Edit a document's text.",
        "input_schema": {"type": "object"},
        "output_schema": None,
        "provider": "command",
        "tier": "write",
        "effects": frozenset({"reads_private"}),
        "reversibility": "undoable",
        "gate": Gate(integration=None, action="artifactr:edit_artifact"),
    }
    return Capability.model_validate(fields | changes)


def context(**changes: Any) -> CallContext:
    """A person's call from portalr, clean, with any fields changed."""
    fields: dict[str, Any] = {
        "scope": HERE,
        "caller": PersonCaller(id="alex"),
        "taint": Clean(),
        "correlation_id": "turn_1",
        "surface": "portalr",
    }
    return CallContext.model_validate(fields | changes)


class PerScope:
    """A provider whose capabilities differ by scope, as a tenant's MCP servers do: it offers
    its capabilities in one scope alone."""

    kind: ProviderKind = "mcp_tool"

    def __init__(self, scope: Scope, *offered: Capability) -> None:
        self._scope = scope
        self._offered = offered

    def capabilities(self, scope: Scope, /) -> Iterable[Capability]:
        return iter(self._offered if scope == self._scope else ())

    async def call(
        self, capability: Capability, arguments: JsonObject, context: CallContext, /
    ) -> ToolResult:
        raise NotImplementedError


# ─── declarations ─────────────────────────────────────────────────────────────


def test_the_vocabularies_are_listed() -> None:
    assert TIERS == ("read", "write", "run_code", "outbound")
    assert EFFECTS == ("reads_private", "reads_untrusted", "sends_out")
    assert len(PROVIDER_KINDS) == 6
    assert capabilities.CONTRACT == "1.0.0"
    assert GROUP == "lattice.capabilities"


@pytest.mark.parametrize(
    "name", ["artifactr.edit_text", "mcp.github.create_issue", "mcp.x.getIssue"]
)
def test_a_name_is_a_provider_and_a_tool(name: str) -> None:
    assert capability(name).name == name


@pytest.mark.parametrize("name", ["edit_text", "Artifactr.edit", "artifactr.", ".edit", "a..b"])
def test_a_name_without_a_provider_and_a_tool_is_refused(name: str) -> None:
    with pytest.raises(ValidationError, match=r"provider\.tool"):
        capability(name)


@pytest.mark.parametrize("version", ["1.0.0", "0.12.3-rc.1", "2.0.0+build.5"])
def test_a_version_is_semantic(version: str) -> None:
    assert capability(version=version).version == version


@pytest.mark.parametrize("version", ["1", "1.0", "v1.0.0", "01.0.0"])
def test_another_version_is_refused(version: str) -> None:
    with pytest.raises(ValidationError, match=r"MAJOR\.MINOR\.PATCH"):
        capability(version=version)


def test_a_description_is_required() -> None:
    with pytest.raises(ValidationError, match="needs a description"):
        capability(description="  ")


def test_limits_are_settings_keys() -> None:
    assert capability(limits=("calls-per-hour:mcp-github",)).limits == (
        "calls-per-hour:mcp-github",
    )
    with pytest.raises(ValidationError, match="settings' keys"):
        capability(limits=("calls per hour",))


def test_a_capability_has_no_risk_class_unless_given() -> None:
    assert capability().risk_class is None
    assert capability(risk_class="admin_high").risk_class == "admin_high"


def test_an_unknown_tier_or_effect_is_refused() -> None:
    with pytest.raises(ValidationError):
        capability(tier="host")
    with pytest.raises(ValidationError):
        capability(effects=frozenset({"network"}))


def test_a_gate_names_an_integration_and_a_grantr_action() -> None:
    gate = Gate(integration="connect:freecad", action="artifactr:edit_artifact")
    assert gate.integration == "connect:freecad"
    assert not gate.different_approver


def test_a_gate_refuses_a_malformed_integration() -> None:
    with pytest.raises(ValidationError, match="integration key"):
        Gate(integration="Connect FreeCAD", action="artifactr:edit_artifact")


def test_a_gate_refuses_a_malformed_action() -> None:
    with pytest.raises(ValidationError, match="package:action"):
        Gate(integration=None, action="edit_artifact")


# ─── call contexts ────────────────────────────────────────────────────────────


def test_a_call_from_lattices_own_surfaces_came_through_no_client() -> None:
    assert context().via is None


def test_a_call_through_a_client_names_it() -> None:
    via = Via(connection_id="conn_1", client_name="Claude", surface="mcp")
    assert context(via=via).via == via


def test_the_caller_is_told_apart_by_its_kind() -> None:
    run = context(caller={"kind": "run", "id": "run_1", "agent": "triage", "on_behalf_of": "alex"})
    assert run.caller == RunCaller(id="run_1", agent="triage", on_behalf_of="alex")
    session = context(caller={"kind": "session", "id": "ses_1"})
    assert session.caller == SessionCaller(id="ses_1")


def test_a_context_round_trips_its_taint() -> None:
    tainted = Tainted(
        causes=(Cause(capability="web.fetch", at=datetime(2026, 10, 31, tzinfo=UTC)),)
    )
    given = context(taint=tainted)
    assert CallContext.model_validate_json(given.model_dump_json()) == given


def test_a_context_needs_its_taint() -> None:
    given = context().model_dump()
    del given["taint"]
    with pytest.raises(ValidationError, match="taint"):
        CallContext.model_validate(given)


# ─── the registry ─────────────────────────────────────────────────────────────


def test_the_registry_lists_its_providers_capabilities_in_order() -> None:
    first, second, third = capability("a.one"), capability("a.two"), capability("b.one")
    commands, builtins = FakeProvider("command", first, second), FakeProvider("builtin", third)
    registry = Registry(commands, builtins)
    assert registry.providers == (commands, builtins)
    assert registry.capabilities(HERE) == (first, second, third)


def test_the_registry_finds_a_capability_and_its_provider() -> None:
    edit = capability()
    commands = FakeProvider("command", edit)
    registry = Registry(commands)
    assert registry.find(HERE, "artifactr.edit_text") == Registered(edit, commands)
    assert registry.find(HERE, "artifactr.delete") is None


def test_an_empty_registry_offers_nothing() -> None:
    assert Registry().capabilities(HERE) == ()


@pytest.mark.parametrize("together", [True, False])
def test_a_name_offered_twice_in_a_scope_is_refused(together: bool) -> None:
    one, other = capability(), capability(description="Edit it otherwise.")
    providers = (
        [FakeProvider("command", one, other)]
        if together
        else [FakeProvider("command", one), FakeProvider("builtin", other)]
    )
    registry = Registry(*providers)
    with pytest.raises(DuplicateCapability, match="offered twice") as refused:
        registry.capabilities(HERE)
    assert (refused.value.name, refused.value.scope) == ("artifactr.edit_text", HERE)
    with pytest.raises(DuplicateCapability):
        registry.find(HERE, "artifactr.edit_text")


def test_a_name_is_refused_only_in_the_scope_that_offers_it_twice() -> None:
    issue = capability("mcp.github.create_issue", provider="mcp_tool")
    registry = Registry(PerScope(HERE, issue), PerScope(THERE, issue))
    assert registry.capabilities(HERE) == (issue,)
    assert registry.capabilities(THERE) == (issue,)
    clashing = Registry(PerScope(HERE, issue), PerScope(HERE, issue))
    with pytest.raises(DuplicateCapability):
        clashing.capabilities(HERE)


def test_the_registry_asks_its_providers_per_scope() -> None:
    issue = capability("mcp.github.create_issue", provider="mcp_tool")
    registry = Registry(PerScope(THERE, issue))
    assert registry.find(HERE, issue.name) is None
    assert registry.find(THERE, issue.name) == Registered(issue, registry.providers[0])


def test_search_matches_every_word_in_the_name_or_description() -> None:
    edit = capability("artifactr.edit_text", description="Edit a document's text.")
    issue = capability("mcp.github.create_issue", description="Open an issue on GitHub.")
    registry = Registry(FakeProvider("command", edit, issue))
    assert registry.search(HERE, "EDIT") == (edit,)
    assert registry.search(HERE, "github issue") == (issue,)
    assert registry.search(HERE, "edit issue") == ()
    assert registry.search(HERE, "  ") == (edit, issue)


# ─── the fake provider ────────────────────────────────────────────────────────


async def test_the_fake_records_each_call_and_returns_what_it_was_given() -> None:
    edit, delete = capability(), capability("artifactr.delete")
    fake = FakeProvider("command", edit, delete, results={edit.name: ToolResult(output={"ok": 1})})
    assert fake.capabilities(THERE) == (edit, delete)
    assert await fake.call(edit, {"text": "hi"}, context()) == ToolResult(output={"ok": 1})
    assert await fake.call(delete, {}, context()) == ToolResult()
    assert fake.calls == [
        FakeCall(edit, {"text": "hi"}, context()),
        FakeCall(delete, {}, context()),
    ]


async def test_the_fake_raises_what_it_was_given() -> None:
    edit = capability()
    fake = FakeProvider("command", edit, results={edit.name: RuntimeError("down")})
    with pytest.raises(RuntimeError, match="down"):
        await fake.call(edit, {}, context())
    assert len(fake.calls) == 1


@pytest.mark.parametrize("kind", PROVIDER_KINDS)
def test_a_fake_of_each_kind_is_a_provider(kind: ProviderKind) -> None:
    fake = FakeProvider(kind, capability(provider=kind))
    assert isinstance(fake, Provider)
    assert fake.kind == kind


# ─── discovery ────────────────────────────────────────────────────────────────


@pytest.fixture
def installed(monkeypatch: pytest.MonkeyPatch) -> list[EntryPoint]:
    """The entry points discovery reads, installed in a module of their own."""
    points: list[EntryPoint] = []
    module = types.ModuleType("installed_capabilities")
    module.__dict__.update(
        commands=FakeProvider("command", capability()),
        builtins=FakeProvider("builtin", capability("web.search")),
        nothing=object(),
    )
    monkeypatch.setitem(sys.modules, module.__name__, module)

    def entry_points(*, group: str) -> list[EntryPoint]:
        return [point for point in points if point.group == group]

    monkeypatch.setattr(capabilities, "entry_points", entry_points)
    return points


def test_discovery_finds_nothing_where_nothing_is_installed(installed: list[EntryPoint]) -> None:
    assert discover() == ()


def test_discovery_loads_each_provider_installed_by_its_name(installed: list[EntryPoint]) -> None:
    installed += [
        EntryPoint("web", "installed_capabilities:builtins", GROUP),
        EntryPoint("artifactr", "installed_capabilities:commands", GROUP),
        EntryPoint("other", "installed_capabilities:nothing", "another.group"),
    ]
    module = sys.modules["installed_capabilities"]
    assert discover() == (module.commands, module.builtins)
    registry = Registry(*discover())
    assert [c.name for c in registry.capabilities(HERE)] == ["artifactr.edit_text", "web.search"]


def test_discovery_reads_the_group_named(installed: list[EntryPoint]) -> None:
    installed.append(EntryPoint("artifactr", "installed_capabilities:commands", "another.group"))
    assert discover("another.group") == (sys.modules["installed_capabilities"].commands,)


def test_discovery_refuses_what_isnt_a_provider(installed: list[EntryPoint]) -> None:
    installed.append(EntryPoint("broken", "installed_capabilities:nothing", GROUP))
    with pytest.raises(TypeError, match="broken = 'installed_capabilities:nothing'"):
        discover()
