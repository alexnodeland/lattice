"""portr's MCP server: lattice's commands, offered to outside clients, called through the enforcer.

:class:`PortrMcp` serves MCP's ``tools/list`` and ``tools/call`` over Streamable HTTP, statelessly,
as the 2026-07-28 revision asks (lattice RFC-0014, portr ADR-0001). It holds no session: every
piece of state across calls is a handle lattice mints and the client passes back, a thread's,
a run's or an approval's id.

- **Every request reads its connection.** The SDK's bearer middleware verifies the access token
  with the application's ``TokenVerifier``, its audience among what it checks, and answers a
  request without one 401, naming the protected resource metadata it serves. portr then asks
  :data:`Connections` for the live connection the token names. A revoked connection, or a token
  that names none, such as a portalr session's, is refused at once.
- **A client is offered its connection's toolsets,** ``core`` always among them, as
  :func:`portr.core.offered` makes them, and can call only what it is offered.
- **A workspace-scoped tool takes a ``workspace`` argument,** required, which portr moves into the
  call's scope. A tenant-wide tool, such as ``artifactr_list_workspaces``, takes none, and is
  called with no workspace (lattice ADR-0044).
- **Every call goes through lattice-core's enforcer,** as the person the connection is for,
  through the client (``CallContext.via``), from surface ``mcp``. A refusal, or a command the
  workspace refuses, is the tool's error; a call that waits for an approval answers its id and
  where a person answers it.
"""

import json
import re
import secrets
from collections.abc import Awaitable, Callable, Iterable, Mapping
from typing import Any, Final

import mcp.types as types
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken, TokenVerifier
from mcp.server.auth.settings import AuthSettings
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings
from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS, INVALID_REQUEST
from pydantic import BaseModel, ConfigDict, Field, JsonValue
from starlette.applications import Starlette

from lattice_core.capabilities import CallContext, PersonCaller, Scope, Via
from lattice_core.commands import Command, Toolset
from lattice_core.enforcement import ApprovalPending, CallFailed, Enforcer, Refused
from lattice_core.taint import Clean
from portr.core import SURFACE, Tool, offered

__all__ = ["WORKSPACE", "Connected", "Connections", "PortrMcp"]

WORKSPACE: Final = "workspace"
"""The argument a workspace-scoped tool takes: the workspace it is called in."""

_WORKSPACE_SCHEMA: Final[dict[str, Any]] = {
    "type": "string",
    "minLength": 1,
    "description": "The workspace to call it in: one that artifactr_list_workspaces lists.",
}

_PLACEHOLDER: Final = re.compile(r"\{([a-z_]+)\}")


class Connected(BaseModel):
    """A live connection: a person's consent that a client may act for them, in one tenant.

    grantr keeps connections (grantr ADR-0043); an application reads one on every request, so a
    revoked connection stops the next call rather than at the token's expiry.
    """

    model_config = ConfigDict(frozen=True, use_attribute_docstrings=True)

    connection_id: str = Field(min_length=1)
    """The connection's id, which audit and each package's actor name."""
    tenant_id: str = Field(min_length=1)
    """The one tenant it is for."""
    person: str = Field(min_length=1)
    """The person every call is checked as."""
    client_name: str = Field(min_length=1)
    """The client's registered name, such as ``Claude``: "Alex via Claude"."""
    toolsets: frozenset[Toolset] = frozenset()
    """The toolsets the person let it use; ``core`` is always added."""


type Connections = Callable[[AccessToken], Awaitable[Connected | None]]
"""The live connection a verified access token names, read on every request, or None."""


class PortrMcp:
    """lattice's commands over MCP, each call through the enforcer.

    Args:
        enforcer: lattice-core's enforcer, whose registry holds the bound providers.
        commands: Every command of the composed catalogs, which the registry's providers serve.
        connections: The live connection an access token names.
        portal: portalr's base URL, such as ``https://lattice.example.com``; a result links to
            its route there, and a pending approval to its page. No links without it.
        name: The server's name, as a client shows it.
        access_token: How a handler reads the request's verified token; the SDK's, but in tests.
    """

    def __init__(
        self,
        enforcer: Enforcer,
        commands: Iterable[Command],
        connections: Connections,
        *,
        portal: str | None = None,
        name: str = "lattice",
        access_token: Callable[[], AccessToken | None] = get_access_token,
    ) -> None:
        self._enforcer = enforcer
        self._commands = tuple(commands)
        self._connections = connections
        self._portal = None if portal is None else portal.rstrip("/")
        self._access_token = access_token
        self.server: Server[Any] = Server(
            name, on_list_tools=self._list_tools, on_call_tool=self._call_tool
        )

    def http_app(
        self, *, auth: AuthSettings, token_verifier: TokenVerifier, **options: Any
    ) -> Starlette:
        """Return the Streamable HTTP app, stateless, behind the SDK's bearer authentication.

        It serves the protected resource metadata at ``/.well-known/oauth-protected-resource``
        for ``auth.resource_server_url``, with ``auth.issuer_url`` its authorization server,
        and answers a request without a valid token 401 naming it. It accepts requests for
        that URL's host alone, as DNS rebinding protection, unless ``transport_security`` says
        otherwise.

        Args:
            auth: The resource server's settings; set ``validate_token_resource`` so only a
                token issued for this server is accepted.
            token_verifier: Verifies each request's bearer token.
            options: More of the SDK's ``streamable_http_app`` options.
        """
        url = auth.resource_server_url
        if "transport_security" not in options and url is not None and url.host is not None:
            hosts = [url.host, f"{url.host}:{url.port}"]
            options["transport_security"] = TransportSecuritySettings(
                enable_dns_rebinding_protection=True,
                allowed_hosts=hosts,
                allowed_origins=[f"{url.scheme}://{host}" for host in hosts],
            )
        return self.server.streamable_http_app(
            stateless_http=True, auth=auth, token_verifier=token_verifier, **options
        )

    async def _connected(self) -> Connected:
        """The request's live connection.

        Raises:
            MCPError: If the request has no verified token, or its token names no live
                connection.
        """
        token = self._access_token()
        connected = None if token is None else await self._connections(token)
        if connected is None:
            raise MCPError(INVALID_REQUEST, "no live connection: connect the client again")
        return connected

    def _offered(self, connected: Connected) -> dict[str, Tool]:
        tools = offered(self._commands, toolsets=connected.toolsets).tools
        return {tool.name: tool for tool in tools}

    async def _list_tools(
        self, _ctx: Any, _params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        connected = await self._connected()
        return types.ListToolsResult(
            tools=[_listed(tool) for tool in self._offered(connected).values()]
        )

    async def _call_tool(
        self, _ctx: Any, params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        connected = await self._connected()
        tool = self._offered(connected).get(params.name)
        if tool is None:
            raise MCPError(INVALID_PARAMS, f"no tool {params.name}")
        arguments = dict(params.arguments or {})
        workspace = None if tool.tenant_wide else arguments.pop(WORKSPACE, None)
        if not tool.tenant_wide and not (isinstance(workspace, str) and workspace):
            return _error(f"{tool.name} is called in a workspace: name one as {WORKSPACE}")
        context = CallContext(
            scope=Scope(tenant_id=connected.tenant_id, workspace_id=workspace),
            caller=PersonCaller(id=connected.person),
            taint=Clean(),
            correlation_id=f"mcp_{secrets.token_hex(8)}",
            surface=SURFACE,
            via=Via(
                connection_id=connected.connection_id,
                client_name=connected.client_name,
                surface="mcp",
            ),
        )
        try:
            called = await self._enforcer.call(tool.command, arguments, context)
        except ApprovalPending as pending:
            return self._pending(connected, pending)
        except Refused as refused:
            return _error(str(refused))
        except CallFailed as failed:
            return _error(str(failed.error))
        values = {"tenant": connected.tenant_id, "workspace": workspace, **arguments}
        return self._answered(called.result.output, tool.route, values)

    def _answered(
        self, output: JsonValue, route: str | None, values: Mapping[str, object]
    ) -> types.CallToolResult:
        text = output if isinstance(output, str) else json.dumps(output)
        content: list[types.ContentBlock] = [types.TextContent(text=text)]
        if self._portal is not None and route is not None:
            content.append(
                types.TextContent(text=f"In portalr: {self._portal}{_filled(route, values)}")
            )
        structured = output if isinstance(output, dict) else None
        return types.CallToolResult(content=content, structured_content=structured)

    def _pending(self, connected: Connected, pending: ApprovalPending) -> types.CallToolResult:
        said = (
            f"This call waits for approval {pending.approval}: a person who may answer it does, "
            "in portalr, and then it can be called again."
        )
        content: list[types.ContentBlock] = [types.TextContent(text=said)]
        if self._portal is not None:
            page = f"/portalr/app/t/{connected.tenant_id}/approvals/{pending.approval}"
            content.append(types.TextContent(text=f"In portalr: {self._portal}{page}"))
        return types.CallToolResult(
            content=content,
            structured_content={"status": "pending", "approval": pending.approval},
        )


def _listed(tool: Tool) -> types.Tool:
    """A tool as MCP lists it: a workspace-scoped one takes ``workspace`` too, required."""
    schema: dict[str, Any] = json.loads(json.dumps(tool.input_schema))
    if not tool.tenant_wide:
        schema.setdefault("type", "object")
        schema["properties"] = {WORKSPACE: _WORKSPACE_SCHEMA, **schema.get("properties", {})}
        schema["required"] = [WORKSPACE, *schema.get("required", [])]
    hints = tool.annotations
    return types.Tool(
        name=tool.name,
        description=tool.description,
        input_schema=schema,
        annotations=types.ToolAnnotations(
            read_only_hint=hints.read_only,
            destructive_hint=hints.destructive,
            idempotent_hint=hints.idempotent,
            open_world_hint=hints.open_world,
        ),
    )


def _filled(route: str, values: Mapping[str, object]) -> str:
    """A route with its placeholders filled, cut before the first segment it can't fill."""
    kept: list[str] = []
    for segment in route.split("/"):
        names = _PLACEHOLDER.findall(segment)
        if any(not isinstance(values.get(name), str) for name in names):
            break
        kept.append(_PLACEHOLDER.sub(lambda match: str(values[match[1]]), segment))
    return "/".join(kept)


def _error(message: str) -> types.CallToolResult:
    return types.CallToolResult(content=[types.TextContent(text=message)], is_error=True)
