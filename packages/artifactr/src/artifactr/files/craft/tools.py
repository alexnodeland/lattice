"""The `tools` dialect: an app whose MCP server has a tool for each step, as WordCraft's has.

A call opens the source with the app's open tool, or makes a blank file with its new tool, runs
the batch with its batch tool, saves with its save tool, and reads what it needs. Each app's
adapter subclasses [`ToolsDialect`][artifactr.files.craft.ToolsDialect], naming its tools and
reading its file into an [`Inspection`][artifactr.files.app.Inspection]; a step whose tool takes
other arguments than WordCraft's is overridden.
"""

from collections.abc import Mapping, Sequence
from typing import ClassVar, override

from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from artifactr.files.app import AppCommand, AppFailed, CommandSpec
from artifactr.files.craft.headless import FOUND, Headless
from artifactr.files.craft.spawn import Server, reply_text


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


class ToolsDialect(Headless):
    """An app whose CLI's MCP server has a tool for each step, spawned for every call.

    A subclass names its app's `craft`, its files' `extension`, its tools, and how it reads a
    file, `inspection`.
    """

    new_tool: ClassVar[str]
    new_arguments: ClassVar[Mapping[str, JsonValue]] = {}
    open_tool: ClassVar[str]
    save_tool: ClassVar[str]
    batch_tool: ClassVar[str] = "batch"
    render_tool: ClassVar[str] = "render_page"
    list_tool: ClassVar[str] = "list_commands"

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the source with the open tool, or make a blank file with the new tool.

        The server holds one file, so its tools name none: None.
        """
        if source is None:
            await server.call(self.new_tool, **self.new_arguments)
            return None
        path = server.source(source, f"source{self.extension}")
        await server.call(self.open_tool, path=str(path))
        return None

    @override
    async def batch(
        self, server: Server, document: JsonValue, commands: Sequence[AppCommand]
    ) -> None:
        """Run the commands as one batch, refused whole, naming the command that failed."""
        steps: list[JsonValue] = [
            {"command": command.name, "params": command.args} for command in commands
        ]
        reply = await server.session.call_tool(self.batch_tool, {"commands": steps})
        if reply.is_error:
            raise AppFailed("refused", _failed_step(reply_text(reply)))

    @override
    async def save(self, server: Server, document: JsonValue) -> bytes:
        """Save the file into the write root with the save tool, and return its bytes."""
        path = server.write_root / f"saved{self.extension}"
        await server.call(self.save_tool, path=str(path))
        return server.saved(path)

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render one page with the render tool, at `scale` pixels per point."""
        return await server.png(self.render_tool, page=page, scale=scale)

    @override
    async def find(self, server: Server, query: str) -> Sequence[CommandSpec]:
        """The commands the list tool finds for the query, ten at most."""
        found = _COMMANDS.validate_json(await server.text(self.list_tool, query=query))
        return [
            CommandSpec(
                name=command.id,
                signature=f"{command.id} {command.params}",
                description=f"{command.label} ({command.location})",
            )
            for command in found[:FOUND]
        ]


def _failed_step(reply: str) -> str:
    """Which command of a batch failed, and why, from the batch's reply."""
    try:
        steps = _STEPS.validate_json(reply)
    except ValidationError:
        return reply
    return next((f"{s.command}: {s.error}" for s in steps if not s.ok), reply)
