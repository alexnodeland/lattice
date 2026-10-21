"""The operator's connection to their app: its server, spawned on stdio for each call.

The server is third-party code, run unsandboxed as the runner's user. It is started for one call,
in an empty temporary directory, under a deadline, and ended with it; its environment is the MCP
SDK's minimal one (`PATH`, `HOME` and the like), the entry's own variables and the secrets the
operator names, so the runner's model keys and everything else stay out. It reaches the app on
the host it is given: loopback, or with `remote=True` a host of the operator's own tailnet, never
without the add-on's token. The app keeps its state, the operator's own session; the server and
lattice keep none (ADR-0085).
"""

import os
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Final, Literal, cast

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, Tool

from artifactr.connect.registry import PROTECTED, ConnectedServer, digest

__all__ = ["LOOPBACK", "Connection", "ConnectionFailed"]

LOOPBACK: Final = frozenset({"127.0.0.1", "localhost", "::1"})
"""The hosts an app is reached on without `remote=True`."""


class ConnectionFailed(Exception):
    """The server didn't start, didn't answer in time, made no sense, or changed a tool."""


class Connection:
    """How the runner reaches an operator's app: its vetted server, started on stdio.

    Args:
        server: The vetted server.
        command: How to start the server, installed ahead at the entry's version from a locked,
            hashed requirement, so nothing is fetched within a call's deadline: the installed
            command, such as `("/opt/connected/freecad/bin/freecad-mcp",)`.
        host: Where the app listens, which the server is given as `--host`.
        port: The app's port, given as `--port`, for a server that takes one.
        remote: Whether a host other than loopback is meant: one on the operator's own tailnet,
            which encrypts and authenticates what the add-on's plain RPC doesn't.
        secrets: The names of variables in the runner's environment the server is given, such
            as `FREECAD_MCP_TOKEN`: read as it is spawned, and passed to nothing else.
        allow: The `code` and `network` tools the operator allows, by the server's name.
        unauthenticated: That the operator allows code and network tools through an add-on that
            takes no token, such as Blender's, which any local process can drive as well.
        scan: Whether a finding in the agent's code is shown to the approver (`warn`), or
            refuses the call before anyone is asked (`block`).
        deadline: The seconds one call may take, the server's start included.

    Raises:
        ValueError: If the host isn't loopback and `remote` isn't given; if `remote` is given
            without the add-on's token; if `allow` names a tool that isn't the server's `code`
            or `network`; or if it names one without the add-on's token, or for an add-on that
            takes none, without `unauthenticated`.
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
    ) -> None:
        if not command:
            raise ValueError("a command starts the server")
        tokened = server.token is not None and server.token in secrets
        if host not in LOOPBACK and not remote:
            raise ValueError(f"{host} isn't loopback: pass remote=True for a host you trust")
        if remote and not tokened:
            raise ValueError(f"a remote {server.title} needs its add-on's token in secrets")
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
        self.server = server
        self.allow = frozenset(allow)
        self.scan = scan
        self.deadline = deadline
        self._command = tuple(command)
        self._options = ("--host", host, *(("--port", str(port)) if port is not None else ()))
        self._secrets = tuple(secrets)
        self._tools: list[Tool] | None = None

    async def tools(self) -> list[Tool]:
        """The tools the server lists, read once in the process and kept."""
        if self._tools is None:
            listed = await self._spawn(lambda session: session.list_tools())
            self._tools = listed.tools
        return self._tools

    async def call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """Call one of the server's tools, once the server it spawned still says it is as vetted.

        The server is a new process for each call, so the tool is checked against its entry's
        digest in the same session that calls it.
        """

        async def checked(session: ClientSession) -> CallToolResult:
            listed = {tool.name: tool for tool in (await session.list_tools()).tools}
            tool = listed.get(name)
            vetted = self.server.tools[name].digest
            if tool is None or digest(name, tool.description, tool.input_schema) != vetted:
                raise ConnectionFailed(f"{name} isn't the tool that was vetted: it wasn't run")
            return await session.call_tool(name, arguments)

        return await self._spawn(checked)

    async def _spawn[T](self, work: Callable[[ClientSession], Awaitable[T]]) -> T:
        """Start the server, do the work, and end it, within the deadline.

        Raises:
            ConnectionFailed: Past the deadline, if the server ended or made no sense, or if
                the work refused.
        """
        command, *arguments = self._command
        env = {**self.server.env, **{n: os.environ[n] for n in self._secrets if n in os.environ}}
        with (
            tempfile.TemporaryDirectory(prefix=f"connect-{self.server.app}-") as directory,
            tempfile.TemporaryFile("w+", errors="replace") as errlog,
        ):
            parameters = StdioServerParameters(
                command=command, args=[*arguments, *self._options], env=env, cwd=directory
            )
            try:
                # anyio's deadline: stdio_client ends the server in a shielded scope.
                with anyio.fail_after(self.deadline):
                    # No sampling, roots or elicitation callback: the session declares none, so
                    # a server can't drive the model or ask a person anything. Its instructions
                    # are never read.
                    async with (
                        stdio_client(parameters, errlog=errlog) as (read, write),
                        ClientSession(read, write) as session,
                    ):
                        await session.initialize()
                        return await work(session)
            except TimeoutError:
                title = self.server.title
                raise ConnectionFailed(f"{title} took more than {self.deadline:.3g}s") from None
            except Exception as error:
                if isinstance(refused := _innermost(error), ConnectionFailed):
                    raise refused from None
                errlog.seek(0)
                printed = errlog.read()[-500:].strip()
                raise ConnectionFailed(f"{refused!r}; it printed: {printed}") from error


def _innermost(error: BaseException) -> BaseException:
    """The first error an exception group holds, however deeply, or the error itself."""
    if isinstance(error, BaseExceptionGroup):
        return _innermost(cast(BaseExceptionGroup[BaseException], error).exceptions[0])
    return error
