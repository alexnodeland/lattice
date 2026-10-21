"""The operator's connection to their app: its server, spawned on stdio for each call.

The server is started where the runner runs, for one call under a deadline, and ended with it;
it reaches the app on the host it is given, loopback unless the operator says otherwise. The app
keeps its state, the operator's own session; the server and lattice keep none (ADR-0085).
"""

import os
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Final, Literal, cast

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, Tool

from artifactr.connect.registry import PROTECTED, ConnectedServer

__all__ = ["LOOPBACK", "Connection", "ConnectionFailed"]

LOOPBACK: Final = frozenset({"127.0.0.1", "localhost", "::1"})
"""The hosts an app is reached on without `remote=True`."""


class ConnectionFailed(Exception):
    """The server didn't start, or didn't answer within the deadline, or made no sense."""


class Connection:
    """How the runner reaches an operator's app: its vetted server, started on stdio.

    Args:
        server: The vetted server.
        command: How to start it, its version pinned: `("uvx", "freecad-mcp==0.1.27")`.
        host: Where the app listens, which the server is given as `--host`.
        port: The app's port, given as `--port`, if not the server's own default.
        remote: Whether a host other than loopback is meant, such as one on the operator's
            tailnet.
        secrets: The names of variables in the runner's environment the server is given, such
            as `FREECAD_MCP_TOKEN`: read as it is spawned, and passed to nothing else.
        allow: The `code` and `network` tools the operator allows, by the server's name.
        scan: Whether a finding in the agent's code is shown to the approver (`warn`), or
            refuses the call before anyone is asked (`block`).
        deadline: The seconds one call may take, the server's start included.

    Raises:
        ValueError: If the host isn't loopback and `remote` isn't given, or `allow` names a tool
            that isn't the server's `code` or `network`.
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
        scan: Literal["warn", "block"] = "warn",
        deadline: float = 30.0,
    ) -> None:
        if host not in LOOPBACK and not remote:
            raise ValueError(f"{host} isn't loopback: pass remote=True for a host you trust")
        if wrong := sorted(name for name in allow if server.tools.get(name) not in PROTECTED):
            raise ValueError(
                f"only {server.title}'s code and network tools are allowed, not {wrong}"
            )
        if not command:
            raise ValueError("a command starts the server")
        self.server = server
        self.allow = frozenset(allow)
        self.scan = scan
        self.deadline = deadline
        self._command = tuple(command)
        self._options = ("--host", host, *(("--port", str(port)) if port is not None else ()))
        self._secrets = tuple(secrets)
        self._tools: list[Tool] | None = None

    async def tools(self) -> list[Tool]:
        """The tools the server lists, read once and kept."""
        if self._tools is None:
            listed = await self._spawn(lambda session: session.list_tools())
            self._tools = listed.tools
        return self._tools

    async def call(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        """Call one of the server's tools."""
        return await self._spawn(lambda session: session.call_tool(name, arguments))

    async def _spawn[T](self, work: Callable[[ClientSession], Awaitable[T]]) -> T:
        """Start the server, do the work, and end it, within the deadline.

        Raises:
            ConnectionFailed: Past the deadline, or if the server ended or made no sense.
        """
        command, *arguments = self._command
        env = {**self.server.env, **{n: os.environ[n] for n in self._secrets if n in os.environ}}
        parameters = StdioServerParameters(
            command=command, args=[*arguments, *self._options], env=env
        )
        with tempfile.TemporaryFile("w+", errors="replace") as errlog:
            try:
                # anyio's deadline: stdio_client ends the server in a shielded scope.
                with anyio.fail_after(self.deadline):
                    # No sampling and no elicitation: a server can't drive the model, or ask a
                    # person anything. Its instructions are never read.
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
                errlog.seek(0)
                printed = errlog.read()[-500:].strip()
                raise ConnectionFailed(f"{_innermost(error)!r}; it printed: {printed}") from error


def _innermost(error: BaseException) -> BaseException:
    """The first error an exception group holds, however deeply, or the error itself."""
    if isinstance(error, BaseExceptionGroup):
        return _innermost(cast(BaseExceptionGroup[BaseException], error).exceptions[0])
    return error
