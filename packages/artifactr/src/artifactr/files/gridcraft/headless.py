"""GridCraft run headless on this machine: a fresh `gridcraft-cli mcp` for every call.

Each call spawns the CLI's MCP server on stdio in an empty temporary directory, opens the bytes
it was given, runs what it was asked, and ends the process and the directory with the call.
GridCraft's server speaks the `tools` dialect, but for its batch: it has none, so each command
is run on its own, by `execute_command`. Its CLI confines nothing, so it runs only on trusted
files until the sandboxed worker runs it (native files ADR-0009), and it renders no page.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, override

from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppCommand, AppFailed, Inspection
from artifactr.files.craft import CRAFTS, Craft, Server, ToolsDialect, reply_text
from artifactr.files.gridcraft.xlsx import (
    XLSX_PACKAGE,
    Sheet,
    fingerprint,
    media_type,
    outline,
    text,
)
from artifactr.files.manifest import XLSX


class _Workbook(BaseModel):
    sheets: list[Sheet] = []


class _Range(BaseModel):
    values: list[list[JsonValue]] = []


class Subprocess(ToolsDialect):
    """GridCraft's headless MCP server, spawned from its CLI on this machine for every call.

    Its CLI reads and writes wherever this process's user can, so it is spawned only with
    `trusted=True`: for tests and trusted files, or inside the sandboxed worker (lattice
    RFC-0003).

    Args:
        cli: The `gridcraft-cli` executable.
        version: The GridCraft version it must be, which provenance records: a call to a CLI of
            another version is refused.
        trusted: Whether its files are trusted, or this process confined: required.
        limit: The most bytes a file may hold, saved or inflated: 256 MiB by default.
        lookup: How long, in seconds, finding commands may take: 10 by default.

    Raises:
        ValueError: If `trusted` isn't given.
    """

    craft: ClassVar[Craft] = CRAFTS["gridcraft"]
    extension: ClassVar[str] = ".xlsx"
    new_tool: ClassVar[str] = "new_workbook"
    open_tool: ClassVar[str] = "open_workbook"
    save_tool: ClassVar[str] = "save_workbook"
    list_argument: ClassVar[str] = "search"
    denied: ClassVar[tuple[str, ...]] = ("file.", "app.")

    def __init__(
        self,
        cli: str | Path,
        *,
        version: str,
        trusted: bool = False,
        limit: int = 256 << 20,
        lookup: float = 10.0,
    ) -> None:
        super().__init__(cli, version=version, trusted=trusted, limit=limit, lookup=lookup)

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the source, refused first unless it is a `.xlsx`, or make a blank workbook.

        GridCraft opens a CSV, or another format it reads, whatever the file is named, and its
        save would make it a `.xlsx`: a file of another format is refused, never converted.

        Raises:
            AppFailed: `refused` if the source isn't a `.xlsx`.
        """
        if source is not None:
            XLSX_PACKAGE.require(source, XLSX, limit=self.limit)
        return await super().open(server, source)

    @override
    async def batch(
        self, server: Server, document: JsonValue, commands: Sequence[AppCommand]
    ) -> None:
        """Run the commands in order, each by `execute_command`, refused at the first that fails.

        The workbook isn't saved once one has failed, so none of the batch is kept.
        """
        self.allowed(commands)
        for command in commands:
            arguments: dict[str, JsonValue] = {"command": command.name, "params": command.args}
            reply = await server.session.call_tool("execute_command", arguments)
            if reply.is_error:
                raise AppFailed("refused", f"{command.name}: {reply_text(reply)}")

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The workbook's sheets and tables, each sheet's cells as shown, and its fingerprint.

        GridCraft lists no comments, and a sheet has no pages.
        """
        workbook = _Workbook.model_validate_json(await server.text("inspect_workbook"))
        sheets: list[str] = []
        for sheet in workbook.sheets:
            cells = await server.text("read_range", sheet=sheet.name, formatted=True)
            sheets.append(text(sheet.name, _Range.model_validate_json(cells).values))
        return Inspection(
            fingerprint=fingerprint(content, limit=self.limit),
            outline=outline(workbook.sheets),
            text="\n\n".join(sheets),
            media_type=media_type(content),
        )
