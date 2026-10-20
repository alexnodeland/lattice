"""PhotoCraft run headless on this machine: a fresh `photocraft-cli mcp` for every call.

PhotoCraft's server is the `commands` dialect's, but for its documents: it refuses `file.open`,
whose paths aren't confined, and opens, makes and saves a document through tools of its own,
`doc_open`, `doc_new` and `doc_save`; its commands act on the document open last, so none is
named; and it renders the flattened image only. What is PhotoCraft's own here is how a document
is read: its layers, their text and its notes, by `doc_inspect`.
"""

import hashlib
from collections.abc import Sequence
from typing import ClassVar, Final, override

from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppFailed, Inspection
from artifactr.files.craft import CRAFTS, PREVIEW, CommandsDialect, Craft, Server
from artifactr.files.manifest import OUTLINE_LIMIT
from artifactr.files.photocraft.psd import form, media_type

BLANK: Final = {"width": 1024, "height": 768}
"""The size, in pixels, of a blank document."""


class _Text(BaseModel):
    text: str = ""


class _Layer(BaseModel):
    name: str
    kind: str = ""
    text: _Text | None = None
    children: list["_Layer"] = []


class _Document(BaseModel):
    layers: list[_Layer] = []
    notes: list[JsonValue] = []


class Subprocess(CommandsDialect):
    """PhotoCraft's headless MCP server, spawned from its CLI on this machine for every call.

    It confines the CLI's file access to the call's own directory, but it is not a sandbox: the
    CLI runs as this process's user, with its network. A document is opened only if its bytes
    are a `.psd`'s, and saved as one; a blank one is 1024 by 768 pixels. It renders the
    flattened image as page 1.
    """

    craft: ClassVar[Craft] = CRAFTS["photocraft"]
    extension: ClassVar[str] = ".psd"
    handle: ClassVar[str | None] = None

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the document with `doc_open`, or make a blank one with `doc_new`.

        Raises:
            AppFailed: `refused` too if the bytes aren't a `.psd`, a `.psb` among them.
        """
        if source is None:
            await server.call("doc_new", **BLANK)
            return None
        if (found := form(source)) != "psd":
            raise AppFailed("refused", f"not a .psd: {'a .psb' if found else 'no PSD header'}")
        await server.call("doc_open", path=str(server.source(source, f"source{self.extension}")))
        return None

    @override
    async def save(self, server: Server, document: JsonValue) -> bytes:
        """Save the document as a `.psd` into the write root with `doc_save`."""
        path = server.write_root / f"saved{self.extension}"
        await server.call("doc_save", path=str(path))
        return server.saved(path)

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render the flattened image, its longer side `PREVIEW` times `scale`.

        Raises:
            AppFailed: `refused` too for any page but the first.
        """
        if page != 1:
            raise AppFailed("refused", f"no page {page}: PhotoCraft renders one flattened image")
        return await server.png("render_preview", max_side=max(1, round(PREVIEW * scale)))

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The document's layers, its type layers' words, its notes, and its format.

        PhotoCraft stamps nothing on a save, so the fingerprint is the bytes' digest.
        """
        found = _Document.model_validate(await server.json("doc_inspect"))
        return Inspection(
            fingerprint=hashlib.sha256(content).hexdigest(),
            outline="\n".join(_outline(found.layers))[:OUTLINE_LIMIT],
            text="\n".join(_words(found.layers)),
            review={"notes": found.notes},
            pages=1,
            media_type=media_type(content),
        )


def _outline(layers: Sequence[_Layer], depth: int = 0) -> list[str]:
    """Each layer's name, top to bottom, indented by the groups it is in."""
    return [
        line
        for layer in layers
        for line in ["  " * depth + layer.name, *_outline(layer.children, depth + 1)]
    ]


def _words(layers: Sequence[_Layer]) -> list[str]:
    """The words of each type layer, top to bottom."""
    return [
        words
        for layer in layers
        for words in [*([layer.text.text] if layer.text else []), *_words(layer.children)]
    ]
