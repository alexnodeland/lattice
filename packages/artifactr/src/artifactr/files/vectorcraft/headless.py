"""VectorCraft run headless on this machine: a fresh `vectorcraft-cli mcp` for every call.

VectorCraft's server is the `commands` dialect's: it opens by `document.open`, saves by
`document.save` and makes a blank document by `file.new`, and its commands act on the document
open last, which none of them names. It renders an artboard, from 0, by `render_preview`. What is
VectorCraft's own here is how a document is read: its artboards, layers and words, by
`doc_inspect`. A save writes every shape as a path and sets the SVG's `<title>` to the file's
name, so a title is not kept.
"""

import hashlib
from typing import ClassVar, override

from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppFailed, Inspection
from artifactr.files.craft import CRAFTS, PREVIEW, CommandsDialect, Craft, Server
from artifactr.files.manifest import OUTLINE_LIMIT
from artifactr.files.vectorcraft.svg import media_type


class _Object(BaseModel):
    name: str = ""
    kind: str = ""
    text: str | None = None
    children: list["_Object"] = []


class _Document(BaseModel):
    artboards: list[JsonValue] = []
    layers: list[_Object] = []


class Subprocess(CommandsDialect):
    """VectorCraft's headless MCP server, spawned from its CLI on this machine for every call.

    It keeps SVGs: a file that isn't one is refused before the CLI starts, so none is saved as
    an SVG from another format. Each artboard is a page. It confines the CLI's file access to the
    call's own directory, but it is not a sandbox (native files ADR-0009).
    """

    craft: ClassVar[Craft] = CRAFTS["vectorcraft"]
    extension: ClassVar[str] = ".svg"
    open_command: ClassVar[str] = "document.open"
    save_command: ClassVar[str] = "document.save"
    new_command: ClassVar[str | None] = "file.new"
    handle: ClassVar[str | None] = None

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the SVG, or make a blank document.

        Raises:
            AppFailed: `refused` too if the bytes aren't an SVG.
        """
        if source is not None and media_type(source) is None:
            raise AppFailed("refused", "not an SVG: its root element isn't svg")
        return await super().open(server, source)

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render the page's artboard, from 0, its longer side `PREVIEW` times `scale`."""
        side = max(1, round(PREVIEW * scale))
        return await server.png("render_preview", artboard=page - 1, max_side=side)

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The document's layers, its words, its artboards as pages, and its format.

        VectorCraft stamps nothing on a save, so the fingerprint is the bytes' digest.
        """
        found = _Document.model_validate(await server.json("doc_inspect"))
        return Inspection(
            fingerprint=hashlib.sha256(content).hexdigest(),
            outline="\n".join(_outline(found.layers))[:OUTLINE_LIMIT],
            text="\n".join(_words(found.layers)),
            pages=len(found.artboards),
            media_type=media_type(content),
        )


def _outline(objects: list[_Object], depth: int = 0) -> list[str]:
    """The layers and groups, indented by depth, each named."""
    return [
        line
        for o in objects
        if o.children or o.kind == "Layer"
        for line in ["  " * depth + o.name, *_outline(o.children, depth + 1)]
    ]


def _words(objects: list[_Object]) -> list[str]:
    """Each type object's words, top to bottom."""
    return [word for o in objects for word in ([o.text] if o.text else []) + _words(o.children)]
