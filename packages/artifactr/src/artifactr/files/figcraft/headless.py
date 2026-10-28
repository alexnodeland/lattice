"""FigCraft run headless on this machine: a fresh `figcraft-cli mcp` for every call.

FigCraft's server is the `tools` dialect's, but for its list, which is text, a command a line;
a blank design, which is the untitled one every session starts with; and a page, which it draws
by going to it and taking its `screenshot`, or, if nothing is on it, as its background alone.
What is FigCraft's own here is how a design is read: its pages and layers by `inspect_document`,
and its comments by `comment.list`. Its CLI confines nothing, so the adapter is made only with
`trusted=True`.
"""

import hashlib
import re
from collections.abc import Sequence
from typing import ClassVar, Final, override

from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppFailed, CommandSpec, Inspection
from artifactr.files.app.png import solid
from artifactr.files.craft import CRAFTS, FOUND, PREVIEW, Craft, Server, ToolsDialect
from artifactr.files.figcraft.design import media_type
from artifactr.files.manifest import OUTLINE_LIMIT

DEPTH: Final = 64
"""How deep `inspect_document` reads each page's layers."""

LISTED: Final = re.compile(
    r"(?P<id>[\w.-]+)\*? — (?P<label>.*?)(?: \[(?P<menu>[^\]]*)\])?(?: \([^)]*\))?"
    r"(?: (?P<params>\{.*))?"
)
"""A line of `list_commands`: its id, `*` if undoable, label, menu, shortcut and parameters."""

EMPTY: Final = "the current page is empty: nothing to render"
"""How FigCraft's `screenshot` refuses a page with no layers: its own words, seen on 0.6.0."""

BACKGROUND: Final = re.compile(r"#(?P<rgb>[0-9A-Fa-f]{6})(?:[0-9A-Fa-f]{2})?")
"""A page's background, `#RRGGBB` or `#RRGGBBAA`; a blank page is drawn opaque, as a canvas is."""


class _Node(BaseModel):
    name: str = ""
    type: str = ""
    background: str = "#FFFFFF"
    characters: str | None = None
    children: list["_Node"] = []


class _Design(BaseModel):
    pages: list[_Node] = []


class _Comments(BaseModel):
    comments: list[JsonValue] = []


class Subprocess(ToolsDialect):
    """FigCraft's headless MCP server, spawned from its CLI on this machine for every call.

    A design is opened only if it is a `.figcraft`, and saved as one; a blank design is the
    untitled one the server starts with. Each canvas page is a page, drawn with its background
    by `screenshot`; an empty one, which FigCraft refuses to draw, is its background alone.

    Its CLI confines nothing: it reads and writes wherever this process's user can, so it is
    made only with `trusted=True`, for trusted files or a process already confined, such as the
    worker, which runs it on hostile ones (native files ADR-0009, ADR-0013).
    """

    craft: ClassVar[Craft] = CRAFTS["figcraft"]
    extension: ClassVar[str] = ".figcraft"
    open_tool: ClassVar[str] = "open_file"
    save_tool: ClassVar[str] = "save_file"

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the design, or keep the untitled one the server starts with for a blank.

        Raises:
            AppFailed: `refused` too if the bytes aren't a `.figcraft`.
        """
        if source is None:
            return None
        if media_type(source) is None:
            raise AppFailed("refused", "not a .figcraft: no document of that format")
        await server.call(self.open_tool, path=str(server.source(source, "source.figcraft")))
        return None

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Go to the page, from 1, and draw it, its longer side at most `PREVIEW` times `scale`.

        A page with nothing on it has no bounds, so FigCraft refuses to draw it. It is drawn as
        what is there, its background: a square of side `PREVIEW` times `scale`, at most
        `PREVIEW`, since a canvas page has no size of its own and a blank one no detail. A blank
        design is new, not damaged.
        """
        await server.call("run_command", command="page.select", params={"index": page - 1})
        side = max(1, round(PREVIEW * scale))
        try:
            return await server.png("screenshot", maxSize=side)
        except AppFailed as failed:
            if failed.failure != "refused" or str(failed) != f"refused: {EMPTY}":
                raise
        design = _Design.model_validate(await server.json("inspect_document", allPages=True))
        shown = design.pages[page - 1].background if page <= len(design.pages) else ""
        blank = min(side, PREVIEW)
        return solid(blank, blank, _rgb(shown))

    @override
    async def find(self, server: Server, query: str) -> Sequence[CommandSpec]:
        """The commands `list_commands` finds for the query, a line each, ten at most."""
        found = (
            LISTED.fullmatch(line)
            for line in (await server.text(self.list_tool, filter=query)).splitlines()
        )
        return [
            CommandSpec(
                name=match["id"],
                signature=f"{match['id']} {match['params']}" if match["params"] else match["id"],
                description=f"{match['label']} ({match['menu']})"
                if match["menu"]
                else match["label"],
            )
            for match in found
            if match
        ][:FOUND]

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The design's pages and layers, its words, its comments, and its format.

        FigCraft stamps nothing on a save, so the fingerprint is the bytes' digest.
        """
        design = _Design.model_validate(
            await server.json("inspect_document", allPages=True, depth=DEPTH)
        )
        comments = _Comments.model_validate(
            await server.json("run_command", command="comment.list", params={"page": "all"})
        )
        return Inspection(
            fingerprint=hashlib.sha256(content).hexdigest(),
            outline=_outline(design),
            text="\n".join(_words(design.pages)),
            review={"comments": comments.comments},
            pages=len(design.pages),
            media_type=media_type(content),
        )


def _rgb(background: str) -> bytes:
    """A page's background as three bytes; white if FigCraft wrote it some other way."""
    match = BACKGROUND.fullmatch(background)
    return bytes.fromhex(match["rgb"] if match else "FFFFFF")


def _outline(design: _Design) -> str:
    """Each page, and its layers indented beneath it, by name."""

    def lines(node: _Node, level: int) -> list[str]:
        nested = [line for child in node.children for line in lines(child, level + 1)]
        return ["  " * level + node.name, *nested]

    return "\n".join(line for page in design.pages for line in lines(page, 0))[:OUTLINE_LIMIT]


def _words(nodes: Sequence[_Node]) -> list[str]:
    """The text layers' words, in the order of the layers."""
    return [
        word
        for node in nodes
        for word in ([node.characters] if node.characters else []) + _words(node.children)
    ]
