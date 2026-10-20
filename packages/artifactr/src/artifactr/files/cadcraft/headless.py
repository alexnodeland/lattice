"""CADCraft run headless on this machine: a fresh `cadcraft-cli mcp` for every call.

CADCraft's server is the `tools` dialect's, but for a batch, which it runs a command at a time
through `execute`, and its list, which is `command_list`'s shape. What is CADCraft's own here is
how a drawing is read: its layers, layouts and entities by `inspect_drawing`, and its words by
`find_text`. Its CLI confines nothing, so the adapter is made only with `trusted=True`.
"""

import hashlib
from collections.abc import Sequence
from typing import ClassVar, Final, override

from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppCommand, AppFailed, CommandSpec, Inspection
from artifactr.files.cadcraft.drawing import EXTENSIONS, media_type
from artifactr.files.craft import CRAFTS, PREVIEW, Craft, Server, ToolsDialect
from artifactr.files.craft.commands import listed
from artifactr.files.craft.spawn import reply_text
from artifactr.files.manifest import DXF, OUTLINE_LIMIT

TEXTS: Final = 10_000
"""The most texts `find_text` is asked for, which the drawing's words are."""


class _Layer(BaseModel):
    name: str


class _Drawing(BaseModel):
    counts: dict[str, int] = {}
    layers: list[_Layer] = []
    layouts: list[str] = []


class _Text(BaseModel):
    text: str


class _Texts(BaseModel):
    texts: list[_Text] = []


class Subprocess(ToolsDialect):
    """CADCraft's headless MCP server, spawned from its CLI on this machine for every call.

    A drawing is opened in the format its bytes are, DXF or DWG, and saved in that format; a
    blank one is a DXF. CADCraft renders its model space, fitted to its extents, as page 1.

    Its CLI confines nothing: it reads and writes wherever this process's user can, so it is
    made only with `trusted=True`, for trusted files or a process already confined, until the
    sandboxed worker runs it (native files ADR-0009).
    """

    craft: ClassVar[Craft] = CRAFTS["cadcraft"]
    extension: ClassVar[str] = EXTENSIONS[DXF]
    new_tool: ClassVar[str] = "new_drawing"
    open_tool: ClassVar[str] = "open"
    save_tool: ClassVar[str] = "save"
    render_tool: ClassVar[str] = "render"

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the drawing by the extension of its format, or make a blank DXF.

        Returns the extension, which it is saved with, so a save keeps its format.

        Raises:
            AppFailed: `refused` too if the bytes are neither a DXF nor a DWG.
        """
        if source is None:
            await server.call(self.new_tool)
            return self.extension
        if (found := media_type(source)) is None:
            raise AppFailed("refused", "not a drawing: neither a DXF nor a DWG")
        extension = EXTENSIONS[found]
        await server.call(self.open_tool, path=str(server.source(source, f"source{extension}")))
        return extension

    @override
    async def batch(
        self, server: Server, document: JsonValue, commands: Sequence[AppCommand]
    ) -> None:
        """Run the commands one at a time through `execute`, refused at the first that fails.

        The server has no batch: a refusal ends the call before the drawing is saved, so the
        batch is refused whole.
        """
        for command in commands:
            reply = await server.session.call_tool(
                "execute", {"command": command.name, "params": command.args}
            )
            if reply.is_error:
                raise AppFailed("refused", f"{command.name}: {reply_text(reply)}")

    @override
    async def save(self, server: Server, document: JsonValue) -> bytes:
        """Save the drawing in the format it was opened in, and return its bytes."""
        path = server.write_root / f"saved{document}"
        await server.call(self.save_tool, path=str(path))
        return server.saved(path)

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render the model space, fitted to its extents, `PREVIEW` times `scale` wide.

        Raises:
            AppFailed: `refused` too for any page but the first.
        """
        if page != 1:
            raise AppFailed("refused", f"no page {page}: CADCraft renders its model space only")
        return await server.png(self.render_tool, width=max(16, round(PREVIEW * scale)))

    @override
    async def find(self, server: Server, query: str) -> Sequence[CommandSpec]:
        """The commands `list_commands` finds for the query, ten at most."""
        return listed(self.list_tool, await server.json(self.list_tool, filter=query))

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The drawing's entities, layers and layouts, its words, and its format.

        CADCraft stamps nothing on a save, so the fingerprint is the bytes' digest.
        """
        drawing = _Drawing.model_validate(await server.json("inspect_drawing"))
        texts = _Texts.model_validate(await server.json("find_text", limit=TEXTS))
        return Inspection(
            fingerprint=hashlib.sha256(content).hexdigest(),
            outline=_outline(drawing),
            text="\n".join(found.text for found in texts.texts),
            pages=1,
            media_type=media_type(content),
        )


def _outline(drawing: _Drawing) -> str:
    """The model space's entities by type, then its layers and its layouts, each a line."""
    parts = {
        "Model": [f"{count} {kind}" for kind, count in drawing.counts.items()],
        "Layers": [layer.name for layer in drawing.layers],
        "Layouts": drawing.layouts,
    }
    lines = [f"{part}: {', '.join(items)}" for part, items in parts.items() if items]
    return "\n".join(lines)[:OUTLINE_LIMIT]
