"""A crafting app's CLI, spawned on this machine as an MCP server on stdio, for one call.

Each call starts the server in an empty temporary directory, holding the root or roots the CLI's
file access is confined to, and ends the process and the directory with the call, so no document
stays open between calls (native files ADR-0004). It is the one place a CLI is started: an
adapter speaks its dialect to the [`Server`][artifactr.files.craft.Server] it is given, and a
sandboxed worker will run the same adapter, and this, inside its sandbox.
"""

import base64
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import cast

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import JsonValue, TypeAdapter, ValidationError

from artifactr.files.app import AppFailed
from artifactr.files.craft.registry import Craft

_JSON: TypeAdapter[JsonValue] = TypeAdapter(JsonValue)


class Server:
    """The CLI's MCP server for one call, and the directories it may read and write.

    Attributes:
        session: The MCP session, initialized.
        read_root: Where the call's source is written, for the CLI to open.
        write_root: Where the CLI saves what it is asked to.
    """

    def __init__(
        self, session: ClientSession, read_root: Path, write_root: Path, limit: int
    ) -> None:
        self.session = session
        self.read_root = read_root
        self.write_root = write_root
        self._limit = limit

    def source(self, content: bytes, name: str) -> Path:
        """Write the call's source into the read root, and return its path."""
        path = self.read_root / name
        path.write_bytes(content)
        return path

    def saved(self, path: Path) -> bytes:
        """The bytes the CLI saved at `path`, refused as too large past the limit."""
        if path.stat().st_size > self._limit:
            raise AppFailed("too_large", f"the saved file is larger than {self._limit} bytes")
        return path.read_bytes()

    async def call(self, tool: str, **arguments: JsonValue) -> CallToolResult:
        """Call a tool, and refuse with its reply's text if it failed."""
        reply = await self.session.call_tool(tool, arguments)
        if reply.is_error:
            raise AppFailed("refused", reply_text(reply))
        return reply

    async def text(self, tool: str, **arguments: JsonValue) -> str:
        """Call a tool, and return its reply's text."""
        return reply_text(await self.call(tool, **arguments))

    async def json(self, tool: str, **arguments: JsonValue) -> JsonValue:
        """Call a tool, and return its reply's structured content, or its text read as JSON.

        Raises:
            AppFailed: `crashed` if it replied with neither.
        """
        reply = await self.call(tool, **arguments)
        if reply.structured_content is not None:
            return reply.structured_content
        try:
            return _JSON.validate_json(reply_text(reply))
        except ValidationError:
            raise AppFailed("crashed", f"{tool} replied with no JSON") from None

    async def png(self, tool: str, **arguments: JsonValue) -> bytes:
        """Call a tool that renders, and return the PNG it replied with."""
        reply = await self.call(tool, **arguments)
        for content in reply.content:
            if isinstance(content, ImageContent) and content.mime_type == "image/png":
                return base64.b64decode(content.data)
        raise AppFailed("crashed", f"{tool} replied with no PNG")


class Spawn:
    """Starts a crafting app's CLI as an MCP server on stdio, once for each call.

    The CLI's file access is confined to the call's own directory by its root flags. An app whose
    CLI confines nothing (its descriptor's `roots` is `none`) reads and writes wherever this
    process's user can, so it is started only when the operator says the files are trusted, or
    that this process is already confined, as the sandboxed worker is. Either way it is not a
    sandbox: the CLI runs as this process's user, with its network.

    Args:
        craft: The app.
        cli: Its CLI, `<app>-cli`.
        version: The version it must be, which provenance records: a CLI of another version is
            refused.
        arguments: What the CLI is given after `mcp`, before the roots.
        trusted: Whether the files are trusted, or this process confined: required of an app
            whose CLI confines nothing.
        limit: The most bytes a saved file may hold.

    Raises:
        ValueError: If the app's CLI confines nothing and `trusted` isn't given.
    """

    def __init__(
        self,
        craft: Craft,
        cli: str | Path,
        *,
        version: str,
        arguments: Sequence[str] = (),
        trusted: bool = False,
        limit: int,
    ) -> None:
        if craft.roots == "none" and not trusted:
            raise ValueError(
                f"{craft.cli} confines no file it reads or writes: run it only on trusted "
                "files, with trusted=True, until the sandboxed worker runs it"
            )
        self.craft = craft
        self.version = version
        self._cli = str(cli)
        self._arguments = tuple(arguments)
        self._limit = limit

    async def run[T](self, deadline: float, work: Callable[[Server], Awaitable[T]]) -> T:
        """Spawn the CLI in a directory of the call's own, do the work, and end both.

        Raises:
            AppFailed: `timeout` past the deadline; `crashed` if the CLI ended, or its replies
                made no sense, mid-call; `refused` if it is another version, or the work refused.
        """
        cli = self.craft.cli
        with tempfile.TemporaryDirectory(prefix=f"{self.craft.name}-") as directory:
            root = Path(directory)
            (root / "in").mkdir()
            (root / "out").mkdir()
            server = StdioServerParameters(
                command=self._cli, args=["mcp", *self._arguments, *self._roots(root)], cwd=root
            )
            with (root / "stderr").open("w+", errors="replace") as errlog:
                try:
                    # anyio's deadline, not asyncio's: stdio_client ends the CLI in a shielded
                    # scope, which only anyio's cancellation leaves to finish.
                    with anyio.fail_after(deadline):
                        async with (
                            stdio_client(server, errlog=errlog) as (read, write),
                            ClientSession(read, write) as session,
                        ):
                            served = Server(session, root / "in", root / "out", self._limit)
                            outcome = await self._attempt(served, work)
                except TimeoutError:
                    raise AppFailed("timeout", f"{cli} took more than {deadline}s") from None
                except Exception as error:
                    # The CLI is a separate process reading hostile bytes: whatever ends it, or
                    # its replies, mid-call is a crash, told with what ended it and the end of
                    # what it printed.
                    errlog.seek(0)
                    printed = errlog.read()[-500:].strip()
                    raise AppFailed(
                        "crashed", f"{_innermost(error)!r}; it printed: {printed}"
                    ) from error
        if isinstance(outcome, AppFailed):
            raise outcome
        return outcome

    def _roots(self, root: Path) -> list[str]:
        """The flags that confine the CLI to the call's directory, as its app takes them."""
        if self.craft.roots == "split":
            return [
                *("--automation-read-root", str(root / "in")),
                *("--automation-write-root", str(root / "out")),
            ]
        return ["--root", str(root)] if self.craft.roots == "single" else []

    async def _attempt[T](
        self, server: Server, work: Callable[[Server], Awaitable[T]]
    ) -> T | AppFailed:
        """The work's result, or how the CLI refused it, kept to raise once the CLI has ended.

        What the body of `stdio_client` and `ClientSession` raises comes out of their task
        groups wrapped in an `ExceptionGroup`, so a refusal is returned through them instead.
        """
        try:
            started = await server.session.initialize()
            if (running := started.server_info.version) != self.version:
                return AppFailed("refused", f"{self.craft.cli} is {running}, not {self.version}")
            return await work(server)
        except AppFailed as failed:
            return failed


def reply_text(reply: CallToolResult) -> str:
    """A reply's text, its text contents joined."""
    return "".join(c.text for c in reply.content if isinstance(c, TextContent))


def _innermost(error: BaseException) -> BaseException:
    """The first error an exception group holds, however deeply, or the error itself."""
    if isinstance(error, BaseExceptionGroup):
        return _innermost(cast(BaseExceptionGroup[BaseException], error).exceptions[0])
    return error
