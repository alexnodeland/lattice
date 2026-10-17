"""WordCraft run headless on this machine: a fresh `wordcraft-cli mcp` for every call.

Each call spawns the CLI's MCP server on stdio, in an empty temporary directory that is its read
root and its write root and nothing else, opens the bytes it was given, runs what it was asked,
and ends the process and the directory with the call. No document stays open between calls.
"""

import asyncio
import base64
import tempfile
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Final

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import CallToolResult, ImageContent, TextContent
from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from artifactr.files.app import AppCommand, AppFailed, Applied, CommandSpec, Inspection, Talk
from artifactr.files.wordcraft.docx import Block, fingerprint, outline

MiB: Final = 1 << 20
FOUND: Final = 10
"""How many commands `commands` returns at most."""

SOURCE: Final = "source.docx"
SAVED: Final = "saved.docx"


class _Text(BaseModel):
    text: str


class _Structure(BaseModel):
    blocks: list[Block] = []
    pages: int | None = None


class _Command(BaseModel):
    id: str
    label: str = ""
    location: str = ""
    params: str = "{}"


class _Step(BaseModel):
    command: str
    ok: bool
    error: str = ""


_COMMANDS = TypeAdapter(list[_Command])
_STEPS = TypeAdapter(list[_Step])
_ITEMS = TypeAdapter(list[JsonValue])


class Subprocess:
    """WordCraft's headless MCP server, spawned from its CLI on this machine for every call.

    It confines the CLI's file access to the call's own directory, but it is not a sandbox: the
    CLI runs as this process's user, with its network. It is for tests and trusted files; the
    sandboxed worker runs hostile ones (lattice RFC-0003).

    Args:
        cli: The `wordcraft-cli` executable.
        version: The WordCraft version it must be, which provenance records: a call to a CLI of
            another version is refused.
        author: Who the CLI says tracked changes, comments and saves are by.
        build: The digest of the image the CLI runs in, if it runs in one.
        limit: The most bytes a file may hold, saved or inflated: 256 MiB by default.
        lookup: How long, in seconds, finding commands may take: 10 by default.
    """

    name: str = "wordcraft"
    talk: Talk = "save"
    """WordCraft's browser build opens and saves files only: people check files out and in."""
    integration: str = "files:wordcraft"

    def __init__(
        self,
        cli: str | Path,
        *,
        version: str,
        author: str = "lattice",
        build: str | None = None,
        limit: int = 256 * MiB,
        lookup: float = 10.0,
    ) -> None:
        self.version: str = version
        self.build: str | None = build
        self._cli = str(cli)
        self._author = author
        self._limit = limit
        self._lookup = lookup

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Applied:
        """Run a batch of commands on a file, or a blank one, and save it.

        The batch stops at the first command that fails, which refuses it whole.
        """

        async def apply(document: _Document) -> Applied:
            await document.open(source)
            if commands:
                await document.batch(commands)
            content = await document.save()
            return Applied(content=content, inspection=await document.inspection(content))

        return await self._call(deadline, apply)

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        """Read a file's fingerprint, outline, text, review and pages."""

        async def inspect(document: _Document) -> Inspection:
            await document.open(source)
            return await document.inspection(source)

        return await self._call(deadline, inspect)

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        """Render one page of a file, from 1, as a PNG, at `scale` pixels per point."""

        async def render(document: _Document) -> bytes:
            await document.open(source)
            return await document.render(page, scale)

        return await self._call(deadline, render)

    async def commands(self, query: str) -> Sequence[CommandSpec]:
        """Find the commands whose id, label or place in the ribbon mentions the query."""

        async def find(document: _Document) -> Sequence[CommandSpec]:
            return await document.commands(query)

        return await self._call(self._lookup, find)

    async def _call[T](self, deadline: float, work: Callable[["_Document"], Awaitable[T]]) -> T:
        """Spawn the CLI in a directory of the call's own, do the work, and end both."""
        with tempfile.TemporaryDirectory(prefix="wordcraft-") as directory:
            root = Path(directory)
            (root / "in").mkdir()
            (root / "out").mkdir()
            server = StdioServerParameters(
                command=self._cli,
                args=[
                    *("mcp", "--author", self._author),
                    *("--automation-read-root", str(root / "in")),
                    *("--automation-write-root", str(root / "out")),
                ],
                cwd=root,
            )
            with (root / "stderr").open("w+") as errlog:
                try:
                    async with asyncio.timeout(deadline):
                        async with (
                            stdio_client(server, errlog=errlog) as (read, write),
                            ClientSession(read, write) as session,
                        ):
                            document = _Document(session, root, self._limit)
                            outcome = await self._attempt(document, work)
                except TimeoutError:
                    late = f"wordcraft-cli took more than {deadline}s"
                    raise AppFailed("timeout", late) from None
                except Exception as error:
                    # The CLI is a separate process reading hostile bytes: whatever ends it, or
                    # its replies, mid-call is a crash, told with the end of what it printed.
                    errlog.seek(0)
                    printed = errlog.read()[-500:].strip()
                    raise AppFailed("crashed", printed or repr(error)) from error
        if isinstance(outcome, AppFailed):
            raise outcome
        return outcome

    async def _attempt[T](
        self, document: "_Document", work: Callable[["_Document"], Awaitable[T]]
    ) -> T | AppFailed:
        """The work's result, or how the CLI refused it, kept to raise once the CLI has ended."""
        try:
            started = await document.session.initialize()
            if (running := started.server_info.version) != self.version:
                return AppFailed("refused", f"wordcraft-cli is {running}, not {self.version}")
            return await work(document)
        except AppFailed as failed:
            return failed


class _Document:
    """The one document a call's server holds, and the tools that act on it."""

    def __init__(self, session: ClientSession, root: Path, limit: int) -> None:
        self.session = session
        self._in = root / "in"
        self._out = root / "out"
        self._limit = limit

    async def open(self, source: bytes | None) -> None:
        if source is None:
            await self._tool("new_document", template="blank")
            return
        path = self._in / SOURCE
        path.write_bytes(source)
        await self._tool("open_document", path=str(path))

    async def batch(self, commands: Sequence[AppCommand]) -> None:
        steps: list[JsonValue] = [
            {"command": command.name, "params": command.args} for command in commands
        ]
        reply = await self._call("batch", {"commands": steps})
        if reply.is_error:
            raise AppFailed("refused", _failed_step(_text(reply)))

    async def save(self) -> bytes:
        path = self._out / SAVED
        await self._tool("save_document", path=str(path))
        if path.stat().st_size > self._limit:
            raise AppFailed("too_large", f"the saved file is larger than {self._limit} bytes")
        return path.read_bytes()

    async def inspection(self, content: bytes) -> Inspection:
        text = _Text.model_validate_json(await self._tool("get_text"))
        structure = _Structure.model_validate_json(await self._tool("inspect_document"))
        comments = _ITEMS.validate_json(await self._tool("execute", command="review.comments"))
        changes = _ITEMS.validate_json(await self._tool("execute", command="review.changes"))
        return Inspection(
            fingerprint=fingerprint(content, limit=self._limit),
            outline=outline(structure.blocks),
            text=text.text,
            review={"comments": comments, "changes": changes},
            pages=structure.pages,
        )

    async def render(self, page: int, scale: float) -> bytes:
        reply = await self._call("render_page", {"page": page, "scale": scale})
        if reply.is_error:
            raise AppFailed("refused", _text(reply))
        for content in reply.content:
            if isinstance(content, ImageContent) and content.mime_type == "image/png":
                return base64.b64decode(content.data)
        raise AppFailed("crashed", "render_page replied with no PNG")

    async def commands(self, query: str) -> Sequence[CommandSpec]:
        found = _COMMANDS.validate_json(await self._tool("list_commands", query=query))
        return [
            CommandSpec(
                name=command.id,
                signature=f"{command.id} {command.params}",
                description=f"{command.label} ({command.location})",
            )
            for command in found[:FOUND]
        ]

    async def _tool(self, name: str, **arguments: JsonValue) -> str:
        """Call a tool, and return its reply's text; refuse with it if the tool failed."""
        reply = await self._call(name, arguments)
        if reply.is_error:
            raise AppFailed("refused", _text(reply))
        return _text(reply)

    async def _call(self, name: str, arguments: dict[str, JsonValue]) -> CallToolResult:
        return await self.session.call_tool(name, arguments)


def _text(reply: CallToolResult) -> str:
    return "".join(c.text for c in reply.content if isinstance(c, TextContent))


def _failed_step(text: str) -> str:
    """Which command of a batch failed, and why, from the batch's reply."""
    try:
        steps = _STEPS.validate_json(text)
    except ValidationError:
        return text
    return next((f"{s.command}: {s.error}" for s in steps if not s.ok), text)
