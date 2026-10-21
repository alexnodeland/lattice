"""The operator's connection to their app: its server, spawned on stdio for each call.

The server is third-party code, run unsandboxed as the runner's user: nothing here contains a
hostile one. It is started for one call, in its own process group, in an empty temporary
directory that is also its `HOME`, under a deadline, and ended with the group; its environment
is the MCP SDK's minimal one (`PATH`, `USER` and the like), the entry's own variables and the
secrets the operator names, so the runner's model keys and everything else stay out. What it
prints to stderr goes nowhere, and none of its words reach the model but its replies, which the
toolset frames. It reaches the app on the host it is given: loopback, or with `remote=True` a
host of the operator's tailnet, never without the add-on's token. Calls to one app run one at a
time. The app keeps its state, the operator's own session; the server and lattice keep none
(ADR-0085).
"""

import ipaddress
import logging
import os
import tempfile
import time
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Final, Literal, cast

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, Tool

from artifactr.connect.registry import PROTECTED, ConnectedServer, digest

__all__ = ["LOOPBACK", "RETRY_AFTER", "TAILNET", "Connection", "ConnectionFailed"]

logger = logging.getLogger("artifactr.connect")

LOOPBACK: Final = frozenset({"127.0.0.1", "::1"})
"""The hosts an app is reached on without `remote=True`: loopback's addresses, not a name that
a resolver could answer otherwise."""

TAILNET: Final = (
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("fd7a:115c:a1e0::/48"),
)
"""The addresses a tailnet gives its machines: a remote host is one of these, or a `.ts.net`
name."""

RETRY_AFTER: Final = 30.0
"""The seconds a failed listing is remembered before the server is asked again."""

_LOCKS: Final[dict[tuple[str, ...], anyio.Lock]] = {}
"""One lock for each app the runner reaches, by its server and address."""


class ConnectionFailed(Exception):
    """The server didn't start, didn't answer in time, made no sense, or isn't as vetted.

    Its message is lattice's own words, never the server's, so it can be shown to the model.
    """


class Connection:
    """How the runner reaches an operator's app: its vetted server, started on stdio.

    Args:
        server: The vetted server.
        command: How to start the server, installed ahead at the entry's release, so nothing
            is fetched within a call's deadline: the installed command, such as
            `("/opt/connected/freecad/bin/freecad-mcp",)`. lattice doesn't verify the install;
            it refuses a server that says it is another version.
        host: The app's address, which the server is given as `--host`.
        port: The app's port, given as `--port`, for a server that takes one.
        remote: That the host is on the operator's tailnet, which encrypts and authenticates
            what the add-on's plain RPC doesn't: a tailnet's address or a `.ts.net` name.
        secrets: The names of variables in the runner's environment the server is given, such
            as `FREECAD_MCP_TOKEN`: read as it is spawned, and passed to nothing else. The
            add-on's token must then be set, or nothing is started.
        allow: The `code` and `network` tools the operator allows, by the server's name.
        unauthenticated: That the operator allows code and network tools through an add-on that
            takes no token, such as Blender's, which any local process can drive as well.
        scan: Whether a finding in the agent's code is shown to the approver (`warn`), or
            refuses the call before anyone is asked (`block`).
        deadline: The seconds one call may take, the server's start included.
        approval_ttl: The seconds an approval holds once asked: an older one runs nothing.

    Raises:
        ValueError: If the host isn't loopback without `remote`, or a tailnet's with it; if
            `remote` is given without the add-on's token; if a port is given to a server that
            takes none; if `allow` names a tool that isn't the server's `code` or `network`,
            or names one without the add-on's token, or, for an add-on that takes none,
            without `unauthenticated`.
    """

    def __init__(
        self,
        server: ConnectedServer,
        *,
        command: Sequence[str],
        host: str = "127.0.0.1",
        port: int | None = None,
        remote: bool = False,
        secrets: Sequence[str] = (),
        allow: Sequence[str] = (),
        unauthenticated: bool = False,
        scan: Literal["warn", "block"] = "warn",
        deadline: float = 30.0,
        approval_ttl: float = 15 * 60,
    ) -> None:
        if not command:
            raise ValueError("a command starts the server")
        tokened = server.token is not None and server.token in secrets
        if remote and not _tailnet(host):
            raise ValueError(f"{host} isn't a tailnet's address or .ts.net name")
        if not remote and host not in LOOPBACK:
            raise ValueError(f"{host} isn't loopback: pass remote=True for a host on your tailnet")
        if remote and not tokened:
            raise ValueError(f"a remote {server.title} needs its add-on's token in secrets")
        if port is not None and not server.ports:
            raise ValueError(f"{server.title}'s server takes no port")
        risks = {name: tool.risk for name, tool in server.tools.items()}
        if wrong := sorted(name for name in allow if risks.get(name) not in PROTECTED):
            raise ValueError(
                f"only {server.title}'s code and network tools are allowed, not {wrong}"
            )
        if allow and not tokened and not (server.token is None and unauthenticated):
            raise ValueError(
                f"code and network tools need {server.token} in secrets"
                if server.token is not None
                else f"{server.title}'s add-on takes no token: allow its code and network "
                "tools only with unauthenticated=True"
            )
        if allow and not tokened:
            logger.warning(
                "%s runs code through an add-on with no token: any local process can too",
                server.title,
            )
        self._server = server
        self._allow = frozenset(allow)
        self._scan: Literal["warn", "block"] = scan
        self._deadline = deadline
        self._approval_ttl = approval_ttl
        self._command = tuple(command)
        self._options = ("--host", host, *(("--port", str(port)) if port is not None else ()))
        self._secrets = tuple(secrets)
        self._tools: list[Tool] | None = None
        self._failed_at: float | None = None
        self._lock = _LOCKS.setdefault((server.app, *self._options), anyio.Lock())

    @property
    def server(self) -> ConnectedServer:
        """The vetted server."""
        return self._server

    @property
    def allow(self) -> frozenset[str]:
        """The `code` and `network` tools the operator allows."""
        return self._allow

    @property
    def scan(self) -> Literal["warn", "block"]:
        """Whether a finding is shown to the approver, or refuses the call."""
        return self._scan

    @property
    def deadline(self) -> float:
        """The seconds one call may take."""
        return self._deadline

    @property
    def approval_ttl(self) -> float:
        """The seconds an approval holds once asked."""
        return self._approval_ttl

    async def tools(self) -> list[Tool]:
        """The tools the server lists, read once in the process and kept.

        Raises:
            ConnectionFailed: If listing failed, now or within the last `RETRY_AFTER` seconds.
        """
        if self._tools is None:
            if self._failed_at is not None and time.monotonic() - self._failed_at < RETRY_AFTER:
                raise ConnectionFailed(f"{self._server.title} didn't answer a moment ago")
            try:
                listed = await self._spawn(lambda session: session.list_tools())
            except ConnectionFailed:
                self._failed_at = time.monotonic()
                raise
            self._tools = listed.tools
        return self._tools

    async def call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """Call one of the server's tools, once the server it spawned still says it is as vetted.

        The server is a new process for each call, so the tool is checked against its entry's
        digest in the same session that calls it. Calls to one app run one at a time.
        """

        async def checked(session: ClientSession) -> CallToolResult:
            listed = {tool.name: tool for tool in (await session.list_tools()).tools}
            tool = listed.get(name)
            vetted = self._server.tools[name].digest
            if tool is None or digest(name, tool.description, tool.input_schema) != vetted:
                raise ConnectionFailed(f"{name} isn't the tool that was vetted: it wasn't run")
            return await session.call_tool(name, arguments)

        async with self._lock:
            return await self._spawn(checked)

    async def _spawn[T](self, work: Callable[[ClientSession], Awaitable[T]]) -> T:
        """Start the server, do the work, and end it, within the deadline.

        Raises:
            ConnectionFailed: Past the deadline, if the add-on's token isn't set, if the server
                ended, made no sense or is another release, or if the work refused.
        """
        server = self._server
        named = {name: os.environ.get(name, "") for name in self._secrets}
        if server.token is not None and server.token in named and not named[server.token]:
            raise ConnectionFailed(f"{server.token} isn't set: {server.title} wasn't started")
        command, *arguments = self._command
        with (
            tempfile.TemporaryDirectory(prefix=f"connect-{server.app}-") as directory,
            open(os.devnull, "w") as nowhere,  # noqa: ASYNC230 (opening /dev/null never blocks)
        ):
            env = {**server.env, **{n: v for n, v in named.items() if v}, "HOME": directory}
            parameters = StdioServerParameters(
                command=command, args=[*arguments, *self._options], env=env, cwd=directory
            )
            try:
                # anyio's deadline: stdio_client ends the server's group in a shielded scope.
                with anyio.fail_after(self._deadline):
                    # No sampling, roots or elicitation callback: the session declares none, so
                    # a server can't drive the model or ask a person anything. Its instructions
                    # are never read.
                    async with (
                        stdio_client(parameters, errlog=nowhere) as (read, write),
                        ClientSession(read, write) as session,
                    ):
                        version = (await session.initialize()).server_info.version
                        if version != server.reported_version:
                            raise ConnectionFailed(
                                f"{server.title}'s server says it is {version!r}, not the "
                                f"vetted {server.reported_version!r}: it wasn't run"
                            )
                        return await work(session)
            except TimeoutError:
                title = server.title
                raise ConnectionFailed(f"{title} took more than {self._deadline:.3g}s") from None
            except Exception as error:
                if isinstance(refused := _innermost(error), ConnectionFailed):
                    raise refused from None
                logger.debug("%s's server failed: %s", server.title, type(refused).__name__)
                raise ConnectionFailed(
                    f"{server.title}'s server ended, or replied with what isn't MCP"
                ) from error


def _tailnet(host: str) -> bool:
    """Whether a host is a tailnet's: one of its addresses, or a `.ts.net` name."""
    if host.endswith(".ts.net"):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in network for network in TAILNET)


def _innermost(error: BaseException) -> BaseException:
    """The first error an exception group holds, however deeply, or the error itself."""
    if isinstance(error, BaseExceptionGroup):
        return _innermost(cast(BaseExceptionGroup[BaseException], error).exceptions[0])
    return error
