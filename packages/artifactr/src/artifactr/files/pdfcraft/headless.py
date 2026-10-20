"""PdfCraft run headless on this machine: a fresh `pdfcraft-cli mcp` for every call.

Each call spawns the CLI's MCP server on stdio, in an empty temporary directory that is its one
root and nothing else, opens the bytes it was given, runs what it was asked, and ends the
process and the directory with the call. PdfCraft's server is the `commands` dialect's first:
what is PdfCraft's own here is how a blank document is made, which no command does headless,
and how a document is read.
"""

from pathlib import Path
from typing import ClassVar, override

from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppFailed, Inspection
from artifactr.files.craft import CRAFTS, CommandsDialect, Craft, Server
from artifactr.files.pdfcraft.pdf import Bookmark, fingerprint, media_type, outline


class _Document(BaseModel):
    outline: list[Bookmark] = []
    pages: list[JsonValue] = []
    repairs: list[str] = []


class _Page(BaseModel):
    text: str = ""


class _Text(BaseModel):
    pages: list[_Page] = []


class _Comments(BaseModel):
    comments: list[JsonValue] = []


class Subprocess(CommandsDialect):
    """PdfCraft's headless MCP server, spawned from its CLI on this machine for every call.

    It confines the CLI's file access to the call's own directory, but it is not a sandbox: the
    CLI runs as this process's user, with its network. It is for tests and trusted files; the
    sandboxed worker runs hostile ones (lattice RFC-0003).

    Args:
        cli: The `pdfcraft-cli` executable.
        version: The PdfCraft version it must be, which provenance records: a call to a CLI of
            another version is refused.
        limit: The most bytes a file may hold, saved or its object streams inflated: 256 MiB by
            default.
        lookup: How long, in seconds, finding commands may take: 10 by default.
    """

    craft: ClassVar[Craft] = CRAFTS["pdfcraft"]
    extension: ClassVar[str] = ".pdf"

    def __init__(
        self, cli: str | Path, *, version: str, limit: int = 256 << 20, lookup: float = 10.0
    ) -> None:
        super().__init__(cli, version=version, limit=limit, lookup=lookup)

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the source by `file.open`, or make a blank page by `doc_create`.

        PdfCraft's command for a blank document, `create.blank`, has no headless tool.
        """
        if source is not None:
            return await super().open(server, source)
        return self.named("doc_create", await server.json("doc_create", **{"from": "blank"}))

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The document's bookmarks, its text by page, its comments, its pages and fingerprint.

        A document PdfCraft had to repair to read, such as one cut short, is refused: its save
        would be PdfCraft's repair of it, not the file.

        Raises:
            AppFailed: `refused` if PdfCraft repaired the document as it read it.
        """
        named = self.params(document, {})
        read = _Document.model_validate(await server.json("doc_inspect", **named))
        if read.repairs:
            raise AppFailed("refused", f"not a whole .pdf: {'; '.join(read.repairs)}")
        text = _Text.model_validate(await server.json("text_extract", **named))
        comments = _Comments.model_validate(await server.json("comment_list", **named))
        return Inspection(
            fingerprint=fingerprint(content, limit=self.limit),
            outline=outline(read.outline),
            text="\n\n".join(page.text for page in text.pages),
            review={"comments": comments.comments},
            pages=len(read.pages),
            media_type=media_type(content),
        )
