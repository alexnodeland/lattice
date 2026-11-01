"""What a client is offered (lattice RFC-0014): the commands of its connection's toolsets offered
on ``mcp``, as tools named ``<package>_<name>`` with annotations from their tier, reversibility
and effects, and the reads exposed as resources as templates."""

from typing import Any

import pytest

from lattice_core.capabilities import Capability, Gate
from lattice_core.commands import Command, NotExposed
from portr.core import CORE, SURFACE, Annotations, offered, tiers


def command(name: str, **changes: Any) -> Command:
    """A command of the core toolset, a write that can be compensated, offered everywhere."""
    capability = Capability.model_validate(
        {
            "name": name,
            "version": "1.0.0",
            "description": f"Do {name}.",
            "input_schema": {"type": "object", "properties": {}},
            "output_schema": None,
            "provider": "command",
            "tier": changes.pop("tier", "write"),
            "effects": changes.pop("effects", frozenset()),
            "reversibility": changes.pop("reversibility", "compensable"),
            "gate": Gate(integration=None, action=f"{name.split('.')[0]}:act"),
        }
    )
    fields: dict[str, Any] = {
        "capability": capability,
        "toolset": "core",
        "exposure": "tool",
        "route": "/portalr/app",
    }
    return Command.model_validate(fields | changes)


POST = command("artifactr.post_message")
READ = command(
    "artifactr.read_thread",
    tier="read",
    reversibility="none",
    effects=frozenset({"reads_private"}),
    exposure="both",
    resource="artifactr://{tenant}/{workspace}/threads/{thread_id}",
)
REVOKE = command("grantr.revoke_key", reversibility="irreversible", toolset="admin")
INVITE = command("portalr.invite_member", effects=frozenset({"sends_out"}), toolset="admin")
ANSWER = command(
    "grantr.answer_approval",
    exposure=NotExposed(reason="approvals come from a person"),
    surfaces=frozenset({"portalr"}),
)
WEBMCP = command("artifactr.set_focus", surfaces=frozenset({"portalr", "webmcp"}))
CATALOG = (POST, READ, REVOKE, INVITE, ANSWER, WEBMCP)


def test_a_connection_is_offered_core_always_and_what_it_was_given() -> None:
    core = offered(CATALOG)
    assert [t.name for t in core.tools] == ["artifactr_post_message", "artifactr_read_thread"]
    admin = offered(CATALOG, toolsets=["admin"])
    assert [t.name for t in admin.tools] == [
        "artifactr_post_message",
        "artifactr_read_thread",
        "grantr_revoke_key",
        "portalr_invite_member",
    ]
    assert (CORE, SURFACE) == ("core", "mcp")


def test_a_command_no_client_reaches_is_offered_to_none() -> None:
    names = {t.command for t in offered(CATALOG, toolsets=["admin"]).tools}
    assert "grantr.answer_approval" not in names, "not exposed"
    assert "artifactr.set_focus" not in names, "not offered on mcp"


def test_a_tool_is_its_command_named_for_a_client() -> None:
    [post, read] = offered(CATALOG).tools
    assert (post.name, post.command, post.toolset) == (
        "artifactr_post_message",
        "artifactr.post_message",
        "core",
    )
    assert post.description == "Do artifactr.post_message."
    assert post.input_schema == {"type": "object", "properties": {}}
    assert post.route == "/portalr/app"
    assert read.annotations == Annotations(
        read_only=True, destructive=False, idempotent=True, open_world=False
    )


def test_annotations_say_a_read_from_a_change_that_cant_be_undone() -> None:
    tools = {t.name: t for t in offered(CATALOG, toolsets=["admin"]).tools}
    assert tools["artifactr_post_message"].annotations == Annotations(
        read_only=False, destructive=False, idempotent=False, open_world=False
    )
    assert tools["grantr_revoke_key"].annotations.destructive
    assert tools["portalr_invite_member"].annotations.open_world
    dumped = tools["grantr_revoke_key"].annotations.model_dump(by_alias=True)
    assert dumped == {
        "readOnlyHint": False,
        "destructiveHint": True,
        "idempotentHint": False,
        "openWorldHint": False,
    }, "as MCP names them"


def test_a_read_exposed_as_a_resource_is_a_template() -> None:
    [resource] = offered(CATALOG).resources
    assert resource.uri_template == "artifactr://{tenant}/{workspace}/threads/{thread_id}"
    assert (resource.command, resource.name, resource.toolset) == (
        "artifactr.read_thread",
        "artifactr_read_thread",
        "core",
    )
    only = command(
        "reflexr.get_run",
        tier="read",
        reversibility="none",
        exposure="resource",
        resource="reflexr://{tenant}/{workspace}/runs/{run_id}",
    )
    found = offered([only])
    assert (found.tools, [r.command for r in found.resources]) == ((), ["reflexr.get_run"])


def test_a_toolset_that_isnt_one_is_refused() -> None:
    given: list[Any] = ["everything"]
    with pytest.raises(ValueError, match="no toolset 'everything'"):
        offered(CATALOG, toolsets=given)


def test_each_toolsets_tiers_for_the_consent_page() -> None:
    held = tiers(CATALOG)
    assert list(held) == ["core", "admin"], "in lattice-core's order, and only those offered"
    assert held["core"] == {"write", "read"}
    assert held["admin"] == {"write"}
