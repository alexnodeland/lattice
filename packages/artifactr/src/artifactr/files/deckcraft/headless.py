"""DeckCraft run headless on this machine: a fresh `deckcraft-cli mcp` for every call.

Each call spawns the CLI's MCP server on stdio in an empty temporary directory, opens the bytes
it was given, runs what it was asked, and ends the process and the directory with the call.
DeckCraft's server speaks the `tools` dialect, with its own names; it renders a slide, numbered
from 0. Its CLI confines nothing, so it runs only on trusted files until the sandboxed worker
runs it (native files ADR-0009).
"""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, override

from pydantic import BaseModel, JsonValue, TypeAdapter

from artifactr.files.app import Inspection
from artifactr.files.craft import CRAFTS, Craft, Server, ToolsDialect
from artifactr.files.deckcraft.pptx import (
    PPTX_PACKAGE,
    Slide,
    fingerprint,
    media_type,
    outline,
    text,
)
from artifactr.files.manifest import PPTX


class _Deck(BaseModel):
    slides: list[JsonValue] = []


_ITEMS = TypeAdapter(list[dict[str, JsonValue]])


class Subprocess(ToolsDialect):
    """DeckCraft's headless MCP server, spawned from its CLI on this machine for every call.

    Its CLI reads and writes wherever this process's user can, so it is spawned only with
    `trusted=True`: for tests and trusted files, or inside the sandboxed worker (lattice
    RFC-0003).

    Args:
        cli: The `deckcraft-cli` executable.
        version: The DeckCraft version it must be, which provenance records: a call to a CLI of
            another version is refused.
        trusted: Whether its files are trusted, or this process confined: required.
        limit: The most bytes a file may hold, saved or inflated: 256 MiB by default.
        lookup: How long, in seconds, finding commands may take: 10 by default.
        launcher: The command the CLI is started under, given the CLI and its arguments, such
            as the worker's `Limits.launcher()`; none by default.

    Raises:
        ValueError: If `trusted` isn't given.
    """

    craft: ClassVar[Craft] = CRAFTS["deckcraft"]
    extension: ClassVar[str] = ".pptx"
    new_tool: ClassVar[str] = "new_presentation"
    open_tool: ClassVar[str] = "open_presentation"
    save_tool: ClassVar[str] = "save_presentation"
    render_tool: ClassVar[str] = "render_slide"
    list_argument: ClassVar[str] = "filter"
    denied: ClassVar[tuple[str, ...]] = ("file.", "app.")

    def __init__(
        self,
        cli: str | Path,
        *,
        version: str,
        trusted: bool = False,
        limit: int = 256 << 20,
        lookup: float = 10.0,
        launcher: Sequence[str] = (),
    ) -> None:
        super().__init__(
            cli, version=version, trusted=trusted, limit=limit, lookup=lookup, launcher=launcher
        )

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the source, refused first unless it is a `.pptx`, or make a deck of a title slide.

        DeckCraft opens its own format whatever the file is named, and its save would make it a
        `.pptx`: a file of another format is refused, never converted.

        Raises:
            AppFailed: `refused` if the source isn't a `.pptx`.
        """
        if source is not None:
            PPTX_PACKAGE.require(source, PPTX, limit=self.limit)
        return await super().open(server, source)

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render one slide, from 1, as DeckCraft numbers them from 0, at `scale` pixels a point."""
        return await server.png(self.render_tool, slide=page - 1, scale=scale)

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The deck's titles, words and notes, its comments, its slides and its fingerprint."""
        deck = _Deck.model_validate_json(await server.text("inspect_document"))
        slides: list[Slide] = []
        comments: list[JsonValue] = []
        for index in range(len(deck.slides)):
            slides.append(
                Slide.model_validate_json(await server.text("inspect_slide", index=index))
            )
            listed = await server.text(
                "run_command", command="comment.list", params={"slide": index}
            )
            comments += [
                {"slide": index + 1, **comment} for comment in _ITEMS.validate_json(listed)
            ]
        return Inspection(
            fingerprint=fingerprint(content, limit=self.limit),
            outline=outline(slides),
            text=text(slides),
            review={"comments": comments},
            pages=len(slides),
            media_type=media_type(content),
        )
