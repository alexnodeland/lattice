"""WordCraft run headless on this machine: a fresh `wordcraft-cli mcp` for every call.

Each call spawns the CLI's MCP server on stdio, in an empty temporary directory that is its read
root and its write root and nothing else, opens the bytes it was given, runs what it was asked,
and ends the process and the directory with the call. No document stays open between calls.
WordCraft's server is the `tools` dialect's first: what is WordCraft's own here is how a
document is read.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import ClassVar, override

from pydantic import BaseModel, JsonValue, TypeAdapter

from artifactr.files.app import Inspection
from artifactr.files.craft import CRAFTS, Craft, Server, ToolsDialect
from artifactr.files.wordcraft.docx import Block, fingerprint, media_type, outline


class _Text(BaseModel):
    text: str


class _Structure(BaseModel):
    blocks: list[Block] = []
    pages: int | None = None


_ITEMS = TypeAdapter(list[JsonValue])


class Subprocess(ToolsDialect):
    """WordCraft's headless MCP server, spawned from its CLI on this machine for every call.

    It confines the CLI's file access to the call's own directory, but it is not a sandbox: the
    CLI runs as this process's user, with its network. It is for tests and trusted files; the
    worker, `artifactr.files.worker`, runs it on hostile ones, inside its sandbox (lattice
    RFC-0003).

    Args:
        cli: The `wordcraft-cli` executable.
        version: The WordCraft version it must be, which provenance records: a call to a CLI of
            another version is refused.
        author: Who the CLI says tracked changes, comments and saves are by.
        limit: The most bytes a file may hold, saved or inflated: 256 MiB by default.
        lookup: How long, in seconds, finding commands may take: 10 by default.
        launcher: The command the CLI is started under, given the CLI and its arguments, such
            as the worker's, which sets its limits first; none by default.
    """

    craft: ClassVar[Craft] = CRAFTS["wordcraft"]
    extension: ClassVar[str] = ".docx"
    new_tool: ClassVar[str] = "new_document"
    new_arguments: ClassVar[Mapping[str, JsonValue]] = {"template": "blank"}
    open_tool: ClassVar[str] = "open_document"
    save_tool: ClassVar[str] = "save_document"

    def __init__(
        self,
        cli: str | Path,
        *,
        version: str,
        author: str = "lattice",
        limit: int = 256 << 20,
        lookup: float = 10.0,
        launcher: Sequence[str] = (),
    ) -> None:
        super().__init__(
            cli,
            version=version,
            arguments=("--author", author),
            limit=limit,
            lookup=lookup,
            launcher=launcher,
        )

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The document's text, headings, comments, tracked changes, pages and fingerprint."""
        text = _Text.model_validate_json(await server.text("get_text"))
        structure = _Structure.model_validate_json(await server.text("inspect_document"))
        comments = _ITEMS.validate_json(await server.text("execute", command="review.comments"))
        changes = _ITEMS.validate_json(await server.text("execute", command="review.changes"))
        return Inspection(
            fingerprint=fingerprint(content, limit=self.limit),
            outline=outline(structure.blocks),
            text=text.text,
            review={"comments": comments, "changes": changes},
            pages=structure.pages,
            media_type=media_type(content),
        )
