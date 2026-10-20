"""A crafting app run headless: the `App` port's four calls, as steps a dialect takes.

Every call spawns the app's CLI (a [`Spawn`][artifactr.files.craft.Spawn]), opens the source or
makes a blank file, does its work and ends: no document stays open between calls. How each step
is asked of the CLI is its dialect's, [`ToolsDialect`][artifactr.files.craft.ToolsDialect] or
[`CommandsDialect`][artifactr.files.craft.CommandsDialect], and how a file is read into an
[`Inspection`][artifactr.files.app.Inspection] is each app's own.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Final

from pydantic import JsonValue

from artifactr.files.app import AppCommand, AppFailed, Applied, CommandSpec, Inspection, Talk
from artifactr.files.craft.registry import Craft
from artifactr.files.craft.spawn import Server, Spawn

FOUND: Final = 10
"""How many commands `commands` returns at most."""


class Headless(ABC):
    """A crafting app's CLI, spawned for every call: an [`App`][artifactr.files.app.App].

    Args:
        cli: The app's CLI, `<app>-cli`.
        version: The version it must be, which provenance records: a CLI of another version is
            refused.
        arguments: What the CLI is given after `mcp`, before the roots.
        trusted: Whether its files are trusted, or this process confined: required of an app
            whose CLI confines nothing.
        limit: The most bytes a file may hold, saved or inflated: 256 MiB by default.
        lookup: How long, in seconds, finding commands may take: 10 by default.
        launcher: The command the CLI is started under, given the CLI and its arguments; none by
            default.

    Raises:
        ValueError: If the app's CLI confines nothing and `trusted` isn't given.
    """

    craft: ClassVar[Craft]
    extension: ClassVar[str]
    """What the source and the saved file are named with, such as `.docx`."""

    build: str | None = None
    """It runs on this machine, in no image."""

    def __init__(
        self,
        cli: str | Path,
        *,
        version: str,
        arguments: Sequence[str] = (),
        trusted: bool = False,
        limit: int = 256 << 20,
        lookup: float = 10.0,
        launcher: Sequence[str] = (),
    ) -> None:
        self.version: str = version
        self.limit = limit
        self._spawn = Spawn(
            self.craft,
            cli,
            version=version,
            arguments=arguments,
            trusted=trusted,
            limit=limit,
            launcher=launcher,
        )
        self._lookup = lookup

    @property
    def name(self) -> str:
        """The app's name, which provenance records."""
        return self.craft.name

    @property
    def talk(self) -> Talk:
        """People check its files out and in: its browser build opens and saves them."""
        return "save"

    @property
    def integration(self) -> str:
        """The key that switches it in a workspace, `files:<name>`."""
        return self.craft.key

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        concrete = not getattr(cls.inspection, "__isabstractmethod__", False)
        if concrete and not all(hasattr(cls, name) for name in ("craft", "extension")):
            raise TypeError(f"{cls.__name__} reads files, so it names its craft and extension")

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Applied:
        """Run a batch of commands on a file, or a blank one, and save it.

        The batch stops at the first command that fails, which refuses it whole.
        """

        async def apply(server: Server) -> Applied:
            document = await self.open(server, source)
            if commands:
                await self.batch(server, document, commands)
            content = await self.save(server, document)
            inspection = await self.inspection(server, document, content)
            return Applied(content=content, inspection=inspection)

        return await self._spawn.run(deadline, apply)

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        """Read a file's fingerprint, outline, text, review and pages."""

        async def inspect(server: Server) -> Inspection:
            document = await self.open(server, source)
            return await self.inspection(server, document, source)

        return await self._spawn.run(deadline, inspect)

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        """Render one page of a file, from 1, as a PNG, at `scale` times the app's own size.

        Raises:
            AppFailed: `refused` too if the app renders no page headless.
        """
        if not self.craft.render:
            raise AppFailed("refused", f"{self.craft.title} renders no page headless")

        async def render(server: Server) -> bytes:
            document = await self.open(server, source)
            return await self.page(server, document, page, scale)

        return await self._spawn.run(deadline, render)

    async def commands(self, query: str) -> Sequence[CommandSpec]:
        """Find the commands whose id, label or place in the app mentions the query."""

        async def find(server: Server) -> Sequence[CommandSpec]:
            return await self.find(server, query)

        return await self._spawn.run(self._lookup, find)

    # ─── the steps, each its dialect's ────────────────────────────────────────
    # Each step after `open` is given what `open` returned: what the server calls the file it
    # opened, for a server whose commands name it, or None.

    @abstractmethod
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the source, or a blank file if it is None, and return what the server calls it."""
        ...

    @abstractmethod
    async def batch(
        self, server: Server, document: JsonValue, commands: Sequence[AppCommand]
    ) -> None:
        """Run the commands in order on the open file, refused whole if one fails."""
        ...

    @abstractmethod
    async def save(self, server: Server, document: JsonValue) -> bytes:
        """Save the open file into the write root, and return its bytes."""
        ...

    @abstractmethod
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render one page of the open file, from 1, as a PNG."""
        ...

    @abstractmethod
    async def find(self, server: Server, query: str) -> Sequence[CommandSpec]:
        """The commands that match the query, ten at most."""
        ...

    @abstractmethod
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """Read the open file, whose bytes are `content`, into an inspection: each app's own."""
        ...
