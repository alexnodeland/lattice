"""portr's MCP server (lattice RFC-0014, portr ADR-0001): what a connection is offered, and each
call through the enforcer, in the workspace it names or, tenant-wide, in none."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx2
import pytest
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp.types import CallToolResult, TextContent
from starlette.applications import Starlette

from lattice_core.approvals import Answerers, FakeApprovals, NoCoverage
from lattice_core.capabilities import (
    CallContext,
    Capability,
    FakeProvider,
    Gate,
    Registry,
    ToolResult,
)
from lattice_core.commands import Command
from lattice_core.enforcement import (
    Enforcer,
    FakeAudit,
    FakeCounter,
    FixedCeilings,
    FixedTaint,
)
from lattice_core.integrations import Defaults
from lattice_core.settings import SettingsDefaults
from portr.mcp import WORKSPACE, Connected, PortrMcp

PORTAL = "https://lattice.example.com"
APP = "/portalr/app/t/{tenant}"
CLAUDE = AccessToken(token="t0k3n", client_id="claude", scopes=[], subject="alex")
ALEX = Connected(
    connection_id="con_0123456789abcdef", tenant_id="acme", person="alex", client_name="Claude"
)


def command(name: str, **changes: Any) -> Command:
    tier = changes.pop("tier", "read")
    reversibility = changes.pop("reversibility", "none" if tier == "read" else "compensable")
    capability = Capability.model_validate(
        {
            "name": name,
            "version": "1.0.0",
            "description": f"{name}, for a test.",
            "input_schema": changes.pop(
                "input_schema",
                {"type": "object", "properties": {}, "additionalProperties": False},
            ),
            "output_schema": None,
            "provider": "command",
            "tier": tier,
            "effects": changes.pop("effects", frozenset()),
            "reversibility": reversibility,
            "gate": Gate(integration=None, action=name.replace(".", ":")),
        }
    )
    fields: dict[str, Any] = {
        "capability": capability,
        "toolset": "core",
        "exposure": "tool",
        "route": f"{APP}/w/{{workspace}}",
    }
    return Command.model_validate(fields | changes)


NOTE = {"type": "object", "properties": {"note_id": {"type": "string"}}, "required": ["note_id"]}
COMMANDS = (
    command("notes.list_spaces", tenant_wide=True, route=APP),
    command("notes.read_note", input_schema=NOTE, route=f"{APP}/w/{{workspace}}/notes/{{note_id}}"),
    command("notes.post", tier="write", effects=frozenset({"sends_out"}), route=None),
    command("notes.erase", tier="write", reversibility="irreversible"),
    command("notes.forbidden"),
    command("notes.broken"),
    command("notes.sensitive", tier="write"),
    command("notes.audit_all", toolset="admin"),
)


class Built:
    """An enforcer over a fake provider of the commands, and a server over it."""

    def __init__(self, *, connected: Connected | None = ALEX, token: AccessToken | None = CLAUDE):
        self.provider = FakeProvider(
            "command",
            *(c.capability for c in COMMANDS),
            results={
                "notes.list_spaces": ToolResult(output="docs\nplans"),
                "notes.read_note": ToolResult(output={"text": "Hello."}),
                "notes.broken": ValueError("the note is gone"),
            },
        )
        self.store = FakeApprovals()

        async def authorize(_context: CallContext, action: str) -> bool:
            return action != "notes:forbidden"

        class Policy:
            async def needed(
                self, capability: Capability, _context: CallContext
            ) -> Answerers | None:
                sensitive = capability.name == "notes.sensitive"
                return Answerers(subjects=frozenset({"sam"})) if sensitive else None

        self.enforcer = Enforcer(
            Registry(self.provider),
            integrations=Defaults({}),
            authorize=authorize,
            ceilings=FixedCeilings(),
            settings=SettingsDefaults({}),
            counter=FakeCounter(),
            taint=FixedTaint(),
            approvals=Policy(),
            coverage=NoCoverage(),
            store=self.store,
            audit=FakeAudit(),
        )

        async def connections(given: AccessToken) -> Connected | None:
            return connected if given.client_id == "claude" else None

        self.mcp = PortrMcp(
            self.enforcer, COMMANDS, connections, portal=PORTAL, access_token=lambda: token
        )


def text(result: CallToolResult) -> list[str]:
    return [block.text for block in result.content if isinstance(block, TextContent)]


async def test_a_connection_is_offered_its_toolsets_and_a_workspace_where_a_tool_needs_one() -> (
    None
):
    async with Client(Built().mcp.server) as client:
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
    assert "notes_audit_all" not in tools, "admin isn't among the connection's toolsets"
    spaces, note = tools["notes_list_spaces"], tools["notes_read_note"]
    assert WORKSPACE not in spaces.input_schema["properties"], "tenant-wide: no workspace"
    assert note.input_schema["required"] == [WORKSPACE, "note_id"]
    assert list(note.input_schema["properties"]) == [WORKSPACE, "note_id"]
    assert note.annotations is not None
    assert note.annotations.read_only_hint
    erase = tools["notes_erase"].annotations
    assert erase is not None
    assert (erase.read_only_hint, erase.destructive_hint) == (False, True)
    post = tools["notes_post"].annotations
    assert post is not None
    assert post.open_world_hint
    with_admin = Built(connected=ALEX.model_copy(update={"toolsets": frozenset({"admin"})}))
    async with Client(with_admin.mcp.server) as client:
        assert "notes_audit_all" in {t.name for t in (await client.list_tools()).tools}


async def test_a_tool_is_called_through_the_enforcer_in_the_workspace_it_names() -> None:
    built = Built()
    async with Client(built.mcp.server) as client:
        read = await client.call_tool("notes_read_note", {WORKSPACE: "docs", "note_id": "n1"})
        spaces = await client.call_tool("notes_list_spaces", {})
    assert not read.is_error
    assert text(read) == [
        '{"text": "Hello."}',
        f"In portalr: {PORTAL}/portalr/app/t/acme/w/docs/notes/n1",
    ]
    assert read.structured_content == {"text": "Hello."}
    assert text(spaces) == ["docs\nplans", f"In portalr: {PORTAL}/portalr/app/t/acme"]
    [reading, listing] = built.provider.calls
    assert reading.arguments == {"note_id": "n1"}, "the workspace is the scope's, not an argument"
    assert (reading.context.scope.tenant_id, reading.context.scope.workspace_id) == ("acme", "docs")
    assert listing.context.scope.workspace_id is None, "tenant-wide: no workspace"
    assert reading.context.caller.id == "alex"
    via = reading.context.via
    assert via is not None
    assert (via.connection_id, via.client_name, via.surface) == (
        ALEX.connection_id,
        "Claude",
        "mcp",
    )
    assert reading.context.surface == "mcp"
    assert reading.context.correlation_id != listing.context.correlation_id


async def test_a_link_stops_before_a_placeholder_it_cant_fill_and_none_without_a_portal() -> None:
    built = Built()
    async with Client(built.mcp.server) as client:
        posted = await client.call_tool("notes_post", {WORKSPACE: "docs"})
        erased = await client.call_tool("notes_erase", {WORKSPACE: "docs"})
        unnamed = await client.call_tool("notes_read_note", {WORKSPACE: "docs", "note_id": 7})
    assert text(posted) == ["null"], "a command with no route links nowhere"
    assert text(erased)[1] == f"In portalr: {PORTAL}/portalr/app/t/acme/w/docs"
    assert text(unnamed)[1] == f"In portalr: {PORTAL}/portalr/app/t/acme/w/docs/notes"
    unlinked = PortrMcp(
        built.enforcer, COMMANDS, lambda _token: _alex(), access_token=lambda: CLAUDE
    )
    async with Client(unlinked.server) as client:
        read = await client.call_tool("notes_read_note", {WORKSPACE: "docs", "note_id": "n1"})
    assert text(read) == ['{"text": "Hello."}']


async def _alex() -> Connected:
    return ALEX


@pytest.mark.parametrize("workspace", [None, "", 3])
async def test_a_workspace_tool_called_with_no_workspace_is_refused(workspace: object) -> None:
    built = Built()
    arguments = {} if workspace is None else {WORKSPACE: workspace}
    async with Client(built.mcp.server) as client:
        refused = await client.call_tool("notes_erase", arguments)
    assert refused.is_error
    assert text(refused) == [f"notes_erase is called in a workspace: name one as {WORKSPACE}"]
    assert built.provider.calls == []


async def test_what_the_enforcer_refuses_or_the_provider_raises_is_the_tools_error() -> None:
    built = Built()
    async with Client(built.mcp.server) as client:
        forbidden = await client.call_tool("notes_forbidden", {WORKSPACE: "docs"})
        broken = await client.call_tool("notes_broken", {WORKSPACE: "docs"})
    assert (forbidden.is_error, text(forbidden)) == (
        True,
        ["the caller doesn't hold notes:forbidden"],
    )
    assert (broken.is_error, text(broken)) == (True, ["the note is gone"])


async def test_a_call_that_waits_for_an_approval_says_where_a_person_answers_it() -> None:
    built = Built()
    async with Client(built.mcp.server) as client:
        waiting = await client.call_tool("notes_sensitive", {WORKSPACE: "docs"})
    assert not waiting.is_error
    assert isinstance(waiting.structured_content, dict)
    approval = waiting.structured_content["approval"]
    assert waiting.structured_content == {"status": "pending", "approval": approval}
    [said, link] = text(waiting)
    assert said.startswith(f"This call waits for approval {approval}")
    assert link == f"In portalr: {PORTAL}/portalr/app/t/acme/approvals/{approval}"
    assert (await built.store.get(approval)).state == "pending"
    unlinked = PortrMcp(
        built.enforcer, COMMANDS, lambda _token: _alex(), access_token=lambda: CLAUDE
    )
    async with Client(unlinked.server) as client:
        again = await client.call_tool("notes_sensitive", {WORKSPACE: "docs"})
    assert len(text(again)) == 1


async def test_only_an_offered_tool_is_called_and_only_on_a_live_connection() -> None:
    async with Client(Built().mcp.server) as client:
        with pytest.raises(MCPError, match="no tool notes_audit_all"):
            await client.call_tool("notes_audit_all", {WORKSPACE: "docs"})
    for built in (Built(connected=None), Built(token=None)):
        async with Client(built.mcp.server) as client:
            with pytest.raises(MCPError, match="no live connection"):
                await client.list_tools()
            with pytest.raises(MCPError, match="no live connection"):
                await client.call_tool("notes_list_spaces", {})


class Verifier:
    """Accepts one token, issued for the server."""

    async def verify_token(self, token: str) -> AccessToken | None:
        if token != CLAUDE.token:
            return None
        return CLAUDE.model_copy(update={"resource": "https://portr.example.com/mcp"})


AUTH = AuthSettings.model_validate(
    {
        "issuer_url": "https://auth.example.com",
        "resource_server_url": "https://portr.example.com/mcp",
        "required_scopes": [],
        "validate_token_resource": True,
    }
)


@asynccontextmanager
async def served() -> AsyncIterator[Starlette]:
    """The HTTP app, running: its lifespan runs the session manager."""
    portr = PortrMcp(Built().enforcer, COMMANDS, lambda token: _connected(token), portal=PORTAL)
    app = portr.http_app(auth=AUTH, token_verifier=Verifier())
    async with app.router.lifespan_context(app):
        yield app


async def _connected(token: AccessToken) -> Connected | None:
    return ALEX if token.client_id == "claude" else None


async def test_over_http_a_request_without_a_token_is_told_where_to_get_one() -> None:
    async with (
        served() as app,
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="https://portr.example.com"
        ) as http,
    ):
        refused = await http.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        metadata = await http.get("/.well-known/oauth-protected-resource/mcp")
    assert refused.status_code == 401
    challenge = refused.headers["www-authenticate"]
    assert challenge.startswith("Bearer ")
    assert "/.well-known/oauth-protected-resource/mcp" in challenge
    described = metadata.json()
    assert described["resource"] == "https://portr.example.com/mcp"
    assert described["authorization_servers"] == ["https://auth.example.com"]


async def test_over_http_a_verified_token_reaches_the_tools() -> None:
    headers = {"Authorization": f"Bearer {CLAUDE.token}"}
    async with (
        served() as app,
        httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app),
            base_url="https://portr.example.com",
            headers=headers,
        ) as http,
        Client(streamable_http_client("https://portr.example.com/mcp", http_client=http)) as client,
    ):
        tools = [tool.name for tool in (await client.list_tools()).tools]
        spaces = await client.call_tool("notes_list_spaces", {})
    assert "notes_list_spaces" in tools
    assert json.dumps(text(spaces)).startswith('["docs')


def test_an_app_without_a_resource_url_or_with_its_own_security_keeps_the_sdks() -> None:
    portr = Built().mcp
    unnamed = AUTH.model_copy(update={"resource_server_url": None})
    own = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    for app in (
        portr.http_app(auth=unnamed, token_verifier=Verifier()),
        portr.http_app(auth=AUTH, token_verifier=Verifier(), transport_security=own),
    ):
        assert "/mcp" in [getattr(route, "path", None) for route in app.routes]
