"""DesignCraft run headless on this machine: a fresh `designcraft-cli mcp` for every call.

DesignCraft's server is the `tools` dialect's, but its save tool writes its own format, so a
layout is opened and saved as IDML by its commands, `file.openIdml` and `file.exportIdml`, run
through `execute`. Its batch says which command failed in an object of its own, its list is
`command_list`'s shape, and it numbers pages from 0. What is DesignCraft's own here is how a
layout is read: its pages and stories by `inspect_document`, and each story's words by
`get_story`.
"""

import hashlib
import json
from collections.abc import Sequence
from typing import ClassVar, Final, override

from pydantic import BaseModel, Field, JsonValue, ValidationError

from artifactr.files.app import AppCommand, AppFailed, CommandSpec, Inspection
from artifactr.files.craft import CRAFTS, Craft, Server, ToolsDialect
from artifactr.files.craft.commands import listed
from artifactr.files.craft.spawn import reply_text
from artifactr.files.designcraft.package import media_type
from artifactr.files.manifest import OUTLINE_LIMIT

STORIES: Final = 1_000
"""The most stories whose words are read, a `get_story` call each: a layout of more is read
only so far, so its stories can't make a call run out its deadline."""


class _Failed(BaseModel):
    command: str = Field(alias="failedCommand")
    error: str


class _Story(BaseModel):
    id: int


class _Layout(BaseModel):
    pages: int = Field(alias="pageCount")
    stories: list[_Story] = []


class _Text(BaseModel):
    text: str


class Subprocess(ToolsDialect):
    """DesignCraft's headless MCP server, spawned from its CLI on this machine for every call.

    A layout is opened only if it is IDML, and saved as IDML: DesignCraft's own save writes its
    native format, and it opens InDesign's `.indd` by converting it, so neither is ever used.

    It confines the CLI's file access to the call's own directory, but it is not a sandbox: the
    CLI runs as this process's user, with its network (native files ADR-0009).
    """

    craft: ClassVar[Craft] = CRAFTS["designcraft"]
    extension: ClassVar[str] = ".idml"
    new_tool: ClassVar[str] = "new_document"
    open_tool: ClassVar[str] = "execute"
    save_tool: ClassVar[str] = "execute"

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the layout by `file.openIdml`, or make a blank one.

        Raises:
            AppFailed: `refused` too if the bytes aren't an IDML package.
        """
        if source is None:
            await server.call(self.new_tool)
            return None
        if media_type(source) is None:
            raise AppFailed("refused", "not an IDML package: its mimetype doesn't say so")
        path = server.source(source, f"source{self.extension}")
        await server.call(self.open_tool, command="file.openIdml", params={"path": str(path)})
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
            raise AppFailed("refused", _failed(reply_text(reply)))

    @override
    async def save(self, server: Server, document: JsonValue) -> bytes:
        """Save the layout as IDML by `file.exportIdml`, and return its bytes."""
        path = server.write_root / f"saved{self.extension}"
        await server.call(self.save_tool, command="file.exportIdml", params={"path": str(path)})
        return server.saved(path)

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render one page with `render_page`, which numbers them from 0."""
        return await server.png(self.render_tool, page=page - 1, scale=scale)

    @override
    async def find(self, server: Server, query: str) -> Sequence[CommandSpec]:
        """The commands `list_commands` finds for the query, ten at most."""
        return listed(self.list_tool, await server.json(self.list_tool, filter=query))

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The layout's stories' words, each story's first line, its pages, and its format.

        DesignCraft stamps nothing on an export, so the fingerprint is the bytes' digest. Only
        the first `STORIES` stories' words are read.
        """
        layout = _Layout.model_validate(await server.json("inspect_document"))
        stories = [
            _Text.model_validate(await server.json("get_story", story=story.id)).text
            for story in layout.stories[:STORIES]
        ]
        lines = [story.strip().splitlines()[0] for story in stories if story.strip()]
        return Inspection(
            fingerprint=hashlib.sha256(content).hexdigest(),
            outline="\n".join(lines)[:OUTLINE_LIMIT],
            text="\n\n".join(stories),
            pages=layout.pages,
            media_type=media_type(content),
        )


def _failed(reply: str) -> str:
    """Which command of a batch failed, and why, from the batch's reply."""
    try:
        failed = _Failed.model_validate(json.loads(reply))
    except (ValueError, ValidationError):
        return reply
    return f"{failed.command}: {failed.error}"
