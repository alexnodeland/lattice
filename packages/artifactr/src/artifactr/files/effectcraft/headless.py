"""EffectCraft run headless on this machine: a fresh `effectcraft-cli mcp` for every call.

EffectCraft's server is the `commands` dialect's, but for its project, which is the one open, so
no command names it; for its open, which says what it repaired; and for its frames, which it
renders at a time in the active composition, a page a second. What is EffectCraft's own here is
how a project is read: its items and the active composition's layers by `doc_inspect`, its text
layers' words by `prop.get`, and its markers by `markers.list`.
"""

import hashlib
import math
from collections.abc import Sequence
from typing import ClassVar, Final, override

from pydantic import BaseModel, Field, JsonValue, TypeAdapter

from artifactr.files.app import AppFailed, Inspection
from artifactr.files.craft import CRAFTS, PREVIEW, CommandsDialect, Craft, Server
from artifactr.files.craft.project import whole
from artifactr.files.effectcraft.project import media_type, outside
from artifactr.files.manifest import OUTLINE_LIMIT

PAGES: Final = 10_000
"""The most pages a project has: its first seconds, ten thousand at most."""

SOURCE_TEXT: Final = "text/sourceText"
"""The property that holds a text layer's words."""

TEXT_LAYERS: Final = 100
"""How many of the active composition's text layers, from the top, its words are read from."""


class _Item(BaseModel):
    id: int
    name: str
    type: str
    parent: int | None = None


class _Layer(BaseModel):
    id: int
    name: str
    type: str


class _Comp(BaseModel):
    name: str
    duration: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    layers: list[_Layer] = []

    @property
    def pages(self) -> int:
        """A page a second it lasts, one at least, `PAGES` at most."""
        return min(PAGES, max(1, math.ceil(min(self.duration, PAGES))))


class _Project(BaseModel):
    items: list[_Item] = []


class _Opened(BaseModel):
    project: _Project
    comp: _Comp | None = Field(default=None, alias="activeComp")


class _Open(BaseModel):
    repaired: list[JsonValue] = []


class _Property(BaseModel):
    value: str = ""


class _Marker(BaseModel):
    time: float = 0.0
    comment: str = ""


_MARKERS = TypeAdapter(list[_Marker])


class Subprocess(CommandsDialect):
    """EffectCraft's headless MCP server, spawned from its CLI on this machine for every call.

    It confines the CLI's file access to the call's own directory, and so its JavaScript, but it
    is not a sandbox: the CLI runs as this process's user, with its network. A project is opened
    only if it is an `.ecproj` with no footage, and saved as one; a blank one is an empty,
    untitled project. Each second of its active composition is a page, the frame at its start
    rendered by `render_preview`; a project with no composition has no page.
    """

    craft: ClassVar[Craft] = CRAFTS["effectcraft"]
    extension: ClassVar[str] = ".ecproj"
    new_command: ClassVar[str | None] = "file.newProject"
    save_command: ClassVar[str] = "file.saveAs"
    handle: ClassVar[str | None] = None

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the project, or make a blank one.

        Raises:
            AppFailed: `refused` too if the bytes aren't an `.ecproj`, hold footage, or are
                what EffectCraft had to repair to open, which a save would write.
        """
        if source is None:
            await server.call("command_run", id=self.new_command, params={})
            return None
        whole(source, self.extension, media_type, outside)
        path = server.source(source, f"source{self.extension}")
        reply = await server.json("command_run", id=self.open_command, params={"path": str(path)})
        if repaired := _Open.model_validate(reply).repaired:
            raise AppFailed("refused", f"EffectCraft repaired the project to open it: {repaired}")
        return None

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render the frame that starts the page's second, its longer side `PREVIEW` times `scale`.

        Raises:
            AppFailed: `refused` too for a page past the active composition, or with none.
        """
        comp = _Opened.model_validate(await server.json("doc_inspect")).comp
        if comp is None or not 1 <= page <= comp.pages:
            pages = comp.pages if comp else 0
            raise AppFailed("refused", f"no page {page}: the project's composition has {pages}")
        side = max(1, round(PREVIEW * scale))
        return await server.png("render_preview", time=page - 1, max_side=side)

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The project's items, its active composition's layers, their words and its markers.

        Its words are its first `TEXT_LAYERS` text layers', each read by a call of its own.

        EffectCraft stamps nothing on a save, so the fingerprint is the bytes' digest.

        Raises:
            AppFailed: `refused` if what a batch made holds footage.
        """
        whole(content, self.extension, media_type, outside)
        found = _Opened.model_validate(await server.json("doc_inspect"))
        comp = found.comp
        words: list[str] = []
        markers: list[JsonValue] = []
        if comp is not None:
            for layer in [layer for layer in comp.layers if layer.type == "Text"][:TEXT_LAYERS]:
                params: JsonValue = {"layer": layer.id, "path": SOURCE_TEXT}
                said = await server.json("command_run", id="prop.get", params=params)
                words.append(_Property.model_validate(said).value)
            listed = await server.json("command_run", id="markers.list", params={})
            markers = [m.model_dump() for m in _MARKERS.validate_python(listed)]
        return Inspection(
            fingerprint=hashlib.sha256(content).hexdigest(),
            outline="\n".join(_outline(found.project.items, comp))[:OUTLINE_LIMIT],
            text="\n".join(words),
            review={"markers": markers},
            pages=comp.pages if comp else 0,
            media_type=media_type(content),
        )


def _outline(items: Sequence[_Item], comp: _Comp | None) -> list[str]:
    """Each item, indented by the folders it is in, then the active composition's layers.

    Each item is listed once, however its project numbers it.
    """
    listed: set[int] = set()

    def under(parent: int | None, depth: int) -> list[str]:
        lines: list[str] = []
        for item in items:
            if item.parent == parent and item.id not in listed:
                listed.add(item.id)
                lines += ["  " * depth + f"{item.name} ({item.type})", *under(item.id, depth + 1)]
        return lines

    lines = under(None, 0)
    if comp is not None:
        lines.append(f"Composition {comp.name}:")
        lines += [f"  {layer.name} ({layer.type})" for layer in comp.layers]
    return lines
