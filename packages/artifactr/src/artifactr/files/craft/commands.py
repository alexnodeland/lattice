"""The `commands` dialect: an app whose MCP server runs every step as one of its commands.

A call opens the source by a command (`file.open`, through `command_run`), which names the open
document, runs the batch through `command_batch`, saves by a command (`file.save`), renders
through `render_preview`, and finds commands through `command_list`, as PdfCraft's server
does, and FilmCraft's in the same dialect. Each app's adapter subclasses
[`CommandsDialect`][artifactr.files.craft.CommandsDialect], naming its commands and reading its
file into an [`Inspection`][artifactr.files.app.Inspection]; a step its server takes otherwise is
overridden.
"""

import json
from collections.abc import Mapping, Sequence
from typing import ClassVar, Final, override

from pydantic import BaseModel, JsonValue, TypeAdapter, ValidationError

from artifactr.files.app import AppCommand, AppFailed, CommandSpec
from artifactr.files.craft.headless import FOUND, Headless
from artifactr.files.craft.spawn import Server, reply_text

PREVIEW: Final = 1024
"""How many pixels a page's longer side is rendered at, at scale 1."""


class _Listed(BaseModel):
    id: str
    label: str = ""
    menu: str | list[str] | None = None
    params: JsonValue = None


class _Result(BaseModel):
    ok: bool
    error: str = ""


class _Batch(BaseModel):
    results: list[_Result] = []


_LISTED = TypeAdapter(list[_Listed])


class CommandsDialect(Headless):
    """An app whose CLI's MCP server runs every step as a command, spawned for every call.

    A subclass names its app's `craft`, its files' `extension`, and how it reads a file,
    `inspection`; and, where they differ from PdfCraft's, its commands and the parameter that
    names the open document.
    """

    open_command: ClassVar[str] = "file.open"
    save_command: ClassVar[str] = "file.save"
    new_command: ClassVar[str | None] = None
    """The command that makes a blank file, or None if the server has none headless."""

    handle: ClassVar[str | None] = "doc"
    """The parameter by which each command names the open document, as the open command's
    result names it; None for a server whose commands act on the document open last."""

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the source, or make a blank file, and return what the server calls it.

        Raises:
            AppFailed: `crashed` too if the open command's result names no document.
        """
        if source is None:
            if self.new_command is None:
                raise AppFailed("refused", f"{self.craft.title} makes no blank file headless")
            command = self.new_command
            opened = await server.json("command_run", id=command, params={})
        else:
            command = self.open_command
            path = server.source(source, f"source{self.extension}")
            opened = await server.json("command_run", id=command, params={"path": str(path)})
        if self.handle is None:
            return None
        if not isinstance(opened, Mapping) or (document := opened.get(self.handle)) is None:
            raise AppFailed("crashed", f"{command} named no document as {self.handle}")
        return document

    @override
    async def batch(
        self, server: Server, document: JsonValue, commands: Sequence[AppCommand]
    ) -> None:
        """Run the commands through `command_batch`, which stops at the first that fails.

        A step its reply says failed refuses the batch, whether the reply is an error or not.
        """
        steps: list[JsonValue] = [
            {"id": command.name, "params": self.params(document, command.args)}
            for command in commands
        ]
        reply = await server.session.call_tool(
            "command_batch", {"steps": steps, "stop_on_error": True}
        )
        failed = _failed_step(commands, reply.structured_content)
        if reply.is_error or failed:
            raise AppFailed("refused", failed or reply_text(reply))

    @override
    async def save(self, server: Server, document: JsonValue) -> bytes:
        """Save the file into the write root by the save command, and return its bytes."""
        path = server.write_root / f"saved{self.extension}"
        params = self.params(document, {"path": str(path)})
        await server.call("command_run", id=self.save_command, params=params)
        return server.saved(path)

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render one page through `render_preview`, its longer side `PREVIEW` times `scale`."""
        side = max(1, round(PREVIEW * scale))
        params = self.params(document, {"page": page, "max_side": side})
        return await server.png("render_preview", **params)

    @override
    async def find(self, server: Server, query: str) -> Sequence[CommandSpec]:
        """The commands `command_list` finds for the query, ten at most."""
        return listed("command_list", await server.json("command_list", filter=query))

    def params(
        self, document: JsonValue, arguments: Mapping[str, JsonValue]
    ) -> dict[str, JsonValue]:
        """A command's parameters, naming the open document as the server called it."""
        if self.handle is None:
            return dict(arguments)
        return {**arguments, self.handle: document}


def listed(tool: str, reply: JsonValue) -> list[CommandSpec]:
    """The first ten commands a list tool replied with, as `command_list` lists them.

    The reply is a list of commands, each its `id`, `label`, `menu` and `params`, or an object
    holding that list as `commands`. A server of the `tools` dialect that lists commands so, as
    CADCraft's does, reads its list with this too.

    Raises:
        AppFailed: `crashed` if the reply holds no list of commands.
    """
    if isinstance(reply, Mapping):
        reply = reply.get("commands", [])
    try:
        found = _LISTED.validate_python(reply)
    except ValidationError as error:
        raise AppFailed("crashed", f"{tool} replied with no commands: {error}") from None
    return [_spec(command) for command in found[:FOUND]]


def _spec(command: _Listed) -> CommandSpec:
    params = command.params if isinstance(command.params, str) else json.dumps(command.params)
    menu = " > ".join(command.menu) if isinstance(command.menu, list) else command.menu
    return CommandSpec(
        name=command.id,
        signature=command.id if command.params is None else f"{command.id} {params}",
        description=f"{command.label} ({menu})" if menu else command.label,
    )


def _failed_step(commands: Sequence[AppCommand], structured: Mapping[str, object] | None) -> str:
    """Which command of a batch failed, and why, from the batch's results; empty if none did."""
    try:
        results = _Batch.model_validate(structured or {}).results
    except ValidationError:
        return ""
    failed = ((c.name, r.error) for c, r in zip(commands, results, strict=False) if not r.ok)
    return next((f"{name}: {error}" for name, error in failed), "")
