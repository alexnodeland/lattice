"""FilmCraft run headless on this machine: a fresh `filmcraft-cli mcp` for every call.

FilmCraft's server is the `commands` dialect's, but for its project, which is the one open, so
no command names it; for its open, which says whether it migrated the project or found media
missing; and for its frames, which it renders at a time in the active sequence, a page a second.
What is FilmCraft's own here is how a project is read: its bins and items, its sequence's clips
and markers by `doc_inspect`, and its captions by `captions.list`. Its CLI confines nothing, so
the adapter is made only with `trusted=True`.
"""

import hashlib
from collections.abc import Sequence
from typing import ClassVar, Final, override

from pydantic import BaseModel, Field, JsonValue

from artifactr.files.app import AppCommand, AppFailed, Inspection
from artifactr.files.craft import CRAFTS, PREVIEW, CommandsDialect, Craft, Server
from artifactr.files.craft.project import whole
from artifactr.files.filmcraft.project import media_type, outside
from artifactr.files.manifest import OUTLINE_LIMIT

TICKS: Final = 254_016_000_000
"""FilmCraft's ticks in a second, by which it times a sequence."""

PAGES: Final = 10_000
"""The most pages a project has: its first seconds, ten thousand at most."""

PATHS: Final = frozenset({"path", "paths", "file", "folder", "dir"})
"""The parameters by which a command names a file or a folder."""


class _Node(BaseModel):
    """A bin, which holds others, or an item, which is of a type."""

    name: str
    type: str = "Bin"
    children: list["_Node"] = []


class _Clip(BaseModel):
    name: str = ""


class _Track(BaseModel):
    name: str
    items: list[_Clip] = []


class _Marker(BaseModel):
    name: str = ""
    comment: str = ""
    start: int = 0


class _Sequence(BaseModel):
    name: str
    duration: int = 0
    video: list[_Track] = []
    audio: list[_Track] = []
    markers: list[_Marker] = []

    @property
    def pages(self) -> int:
        """A page a second it lasts, one at least, `PAGES` at most."""
        return min(PAGES, max(1, -(-self.duration // TICKS)))


class _Project(BaseModel):
    root: _Node


class _Opened(BaseModel):
    project: _Project
    sequence: _Sequence | None = None


class _Caption(BaseModel):
    text: str = ""


class _CaptionTrack(BaseModel):
    captions: list[_Caption] = []


class _Captions(BaseModel):
    tracks: list[_CaptionTrack] = []


class _Open(BaseModel):
    migrated: bool = False
    missing: int = Field(default=0, alias="missingMedia")


class Subprocess(CommandsDialect):
    """FilmCraft's headless MCP server, spawned from its CLI on this machine for every call.

    A project is opened only if it is a `.fcproj` of FilmCraft's own release that draws nothing
    from outside it, and saved as one; a blank one is an empty, untitled project. Each second of
    its active sequence is a page, the frame at its start rendered by `render_preview`; a
    project with no sequence has no page.

    Its CLI confines nothing: it reads and writes wherever this process's user can, so it is
    made only with `trusted=True`, for trusted files or a process already confined, such as the
    worker, which runs it on hostile ones (native files ADR-0009, ADR-0013).
    """

    craft: ClassVar[Craft] = CRAFTS["filmcraft"]
    extension: ClassVar[str] = ".fcproj"
    new_command: ClassVar[str | None] = "file.newProject"
    save_command: ClassVar[str] = "file.saveCopy"
    handle: ClassVar[str | None] = None
    denied: ClassVar[tuple[str, ...]] = (
        *("file.open", "file.save", "file.close", "file.revert", "file.recover", "file.importAaf"),
        *("file.export", "file.autoSave", "file.listAutoSaves", "file.discardRecovery"),
        *("export.", "mediaBrowser.", "media.", "lut.", "presets.", "shortcuts.", "labels."),
        *("graphics.template.", "graphics.newFromFile", "tts.", "app."),
        *(
            "file.projectSettings.scratchDisks",
            "file.newProjectFromTemplate",
            "file.newOfflineFile",
        ),
    )
    """The commands that read or write a file, or reach past the project: its CLI confines
    nothing, so no batch runs them."""

    @override
    def allowed(self, commands: Sequence[AppCommand]) -> None:
        """Refuse a batch that holds a denied command, or a command given a path.

        Raises:
            AppFailed: `refused`, naming the command.
        """
        super().allowed(commands)
        if found := next((c.name for c in commands if PATHS & set(c.args)), None):
            raise AppFailed("refused", f"{found}: FilmCraft's adapter gives no command a path")

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the project, or make a blank one.

        Raises:
            AppFailed: `refused` too if the bytes aren't a `.fcproj`, draw media from outside
                it, or are of an older release's, which a save would migrate.
        """
        if source is None:
            await server.call("command_run", id=self.new_command, params={})
            return None
        whole(source, self.extension, media_type, outside)
        path = server.source(source, f"source{self.extension}")
        reply = await server.json("command_run", id=self.open_command, params={"path": str(path)})
        opened = _Open.model_validate(reply)
        if opened.migrated:
            raise AppFailed("refused", "an older release's project, which a save would migrate")
        if opened.missing:
            raise AppFailed("refused", f"the project misses {opened.missing} media files")
        return None

    @override
    async def page(self, server: Server, document: JsonValue, page: int, scale: float) -> bytes:
        """Render the frame that starts the page's second, its longer side `PREVIEW` times `scale`.

        Raises:
            AppFailed: `refused` too for a page past the active sequence, or with none.
        """
        found = _Opened.model_validate(await server.json("doc_inspect")).sequence
        if found is None or not 1 <= page <= found.pages:
            pages = found.pages if found else 0
            raise AppFailed("refused", f"no page {page}: the project's sequence has {pages}")
        side = max(1, round(PREVIEW * scale))
        return await server.png("render_preview", seconds=page - 1, max_side=side)

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The project's bins and items, its sequence's clips, its captions and its markers.

        FilmCraft stamps nothing on a save, so the fingerprint is the bytes' digest.

        Raises:
            AppFailed: `refused` if what a batch made draws media from outside the project.
        """
        whole(content, self.extension, media_type, outside)
        found = _Opened.model_validate(await server.json("doc_inspect"))
        reply = await server.json("command_run", id="captions.list", params={})
        captions = _Captions.model_validate(reply)
        sequence = found.sequence
        return Inspection(
            fingerprint=hashlib.sha256(content).hexdigest(),
            outline="\n".join(_outline(found.project.root.children, sequence))[:OUTLINE_LIMIT],
            text="\n".join(c.text for track in captions.tracks for c in track.captions),
            review={"markers": [m.model_dump() for m in sequence.markers] if sequence else []},
            pages=sequence.pages if sequence else 0,
            media_type=media_type(content),
        )


def _outline(nodes: Sequence[_Node], sequence: _Sequence | None, depth: int = 0) -> list[str]:
    """Each bin and item, indented by the bins it is in, then the sequence's tracks' clips."""
    lines = [
        line
        for node in nodes
        for line in [
            "  " * depth
            + (f"{node.name}/" if node.type == "Bin" else f"{node.name} ({node.type})"),
            *_outline(node.children, None, depth + 1),
        ]
    ]
    if sequence is not None:
        lines.append(f"Sequence {sequence.name}:")
        lines += [
            f"  {track.name}: {', '.join(clip.name for clip in track.items)}"
            for track in (*sequence.video, *sequence.audio)
            if track.items
        ]
    return lines
