"""Commands (lattice RFC-0014, ADR-0041): a capability plus what a surface needs, declared in a
static catalog, with tool names that never collide."""

from collections.abc import AsyncIterator, Iterable
from typing import Any

import pytest
from pydantic import ValidationError

from lattice_core.capabilities import Capability, Gate, Scope
from lattice_core.commands import (
    EXTENSION,
    SURFACES,
    TOOLSETS,
    Command,
    Commands,
    Frames,
    NoCommand,
    NotExposed,
    ResourceChanged,
    Watch,
    called,
    calls,
    calls_none,
    carries_frames,
    catalog,
    contract_schema,
    tool_name,
)


def capability(name: str = "artifactr.post_message", **changes: Any) -> Capability:
    fields: dict[str, Any] = {
        "name": name,
        "version": "1.0.0",
        "description": "Post a message in a thread.",
        "input_schema": {"type": "object"},
        "output_schema": None,
        "provider": "command",
        "tier": "write",
        "effects": frozenset(),
        "reversibility": "compensable",
        "gate": Gate(integration=None, action="artifactr:post_message"),
    }
    return Capability.model_validate(fields | changes)


def command(name: str = "artifactr.post_message", **changes: Any) -> Command:
    fields: dict[str, Any] = {
        "capability": capability(name),
        "toolset": "core",
        "exposure": "tool",
        "route": "/t/{tenant}/w/{workspace}/threads/{thread_id}",
    }
    return Command.model_validate(fields | changes)


class Catalog:
    def __init__(self, *commands: Command) -> None:
        self._commands = commands

    def commands(self) -> Iterable[Command]:
        return self._commands


def test_a_command_is_a_capability_offered_on_every_surface_by_default() -> None:
    made = command()
    assert (made.name, made.tool) == ("artifactr.post_message", "artifactr_post_message")
    assert made.surfaces == SURFACES == frozenset({"portalr", "mcp", "acp", "webmcp"})
    assert made.resource is None
    assert TOOLSETS == ("core", "automations", "research", "code", "files", "feedback", "admin")


def test_a_read_may_be_a_resource_and_a_command_may_be_no_tool() -> None:
    read = command(
        "artifactr.read_artifact",
        exposure="both",
        resource="artifactr://{tenant}/{workspace}/artifacts/{artifact_id}",
    )
    assert read.exposure == "both"
    hidden = command(
        "grantr.answer_approval",
        exposure=NotExposed(reason="approvals come from a person"),
        surfaces=frozenset({"portalr"}),
    )
    assert isinstance(hidden.exposure, NotExposed)


@pytest.mark.parametrize(
    ("changes", "says"),
    [
        ({"capability": capability(provider="mcp_tool")}, "is a mcp_tool capability"),
        ({"capability": capability("mcp.github.create_issue")}, "is <package>.<name>"),
        ({"capability": capability("artifactr.Post")}, "is <package>.<name>"),
        ({"capability": capability("a." + "b" * 63)}, "longer than 64 characters"),
        ({"exposure": "resource"}, "names its URI template"),
        ({"resource": "artifactr://{tenant}"}, "so it is exposed as one"),
        ({"surfaces": frozenset()}, "is offered on some surface"),
        ({"toolset": "everything"}, "'core', 'automations'"),
    ],
)
def test_a_command_is_refused_unless_well_formed(changes: dict[str, Any], says: str) -> None:
    with pytest.raises(ValidationError, match=says):
        Command.model_validate(
            {
                "capability": capability(),
                "toolset": "core",
                "exposure": "tool",
                "route": None,
            }
            | changes
        )


def test_a_not_exposed_command_says_why() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        NotExposed(reason="")


def test_a_tool_name_is_the_name_with_its_dot_an_underscore() -> None:
    assert tool_name("grantr.issue_key") == "grantr_issue_key"


def test_the_catalog_composes_and_refuses_a_name_or_a_tool_twice() -> None:
    post, read = command(), command("artifactr.read_artifact")
    issue = command("grantr.issue_key")
    composed = catalog(Catalog(post, read), Catalog(issue))
    assert list(composed) == [
        "artifactr.post_message",
        "artifactr.read_artifact",
        "grantr.issue_key",
    ]
    assert isinstance(Catalog(), Commands)
    with pytest.raises(ValueError, match=r"two commands are named artifactr\.post_message"):
        catalog(Catalog(post), Catalog(post))
    with pytest.raises(ValueError, match=r"a\.b_c and a_b\.c are both the tool a_b_c"):
        catalog(Catalog(command("a_b.c")), Catalog(command("a.b_c")))


def test_an_operation_says_the_command_it_calls_or_one_of_several() -> None:
    assert calls("grantr.list_members") == {EXTENSION: "grantr.list_members"}
    both = calls("grantr.grant", "grantr.grant_on_tenant")
    assert both == {"x-lattice-command": ["grantr.grant", "grantr.grant_on_tenant"]}
    assert called(both[EXTENSION]) == ("grantr.grant", "grantr.grant_on_tenant")
    assert called("grantr.list_members") == ("grantr.list_members",)
    with pytest.raises(ValueError, match="not 'grantr:list_members'"):
        calls("grantr.list_members", "grantr:list_members")


def test_an_operation_says_it_carries_frames_or_why_it_calls_none() -> None:
    frames = carries_frames("command")[EXTENSION]
    assert called(frames) == Frames(frames="command")
    watching = carries_frames("command", watch_run="the stream's alone")[EXTENSION]
    assert called(watching) == Frames(frames="command", none={"watch_run": "the stream's alone"})
    with pytest.raises(ValidationError):
        carries_frames("command", watch_run="")
    nothing = calls_none("the UIs' configuration, which anyone may read")[EXTENSION]
    assert called(nothing) == NoCommand(none="the UIs' configuration, which anyone may read")
    with pytest.raises(ValidationError):
        calls_none("")


@pytest.mark.parametrize(
    "extension",
    [None, "grantr:list_members", "list_members", [], ["grantr.grant"], {"frames": ""}, {}],
)
def test_an_operation_that_says_nothing_readable_is_refused(extension: Any) -> None:
    with pytest.raises(ValidationError):
        called(extension)


class Changes:
    async def changes(self, scope: Scope, /) -> AsyncIterator[ResourceChanged]:
        yield ResourceChanged(
            uri=f"artifactr://{scope.tenant_id}/{scope.workspace_id}/artifacts/a1"
        )


async def test_a_bound_provider_watches_its_resources() -> None:
    watch = Changes()
    assert isinstance(watch, Watch)
    [changed] = [c async for c in watch.changes(Scope(tenant_id="acme", workspace_id="docs"))]
    assert changed.uri == "artifactr://acme/docs/artifacts/a1"
    with pytest.raises(ValidationError):
        ResourceChanged(uri="")


def test_the_contracts_schema_is_a_commands() -> None:
    schema = contract_schema()
    assert schema["title"] == "lattice.commands 1.0.0"
    assert schema["required"] == ["capability", "toolset", "exposure", "route"]
