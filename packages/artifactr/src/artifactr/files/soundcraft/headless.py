"""SoundCraft run headless on this machine: a fresh `soundcraft-cli mcp` for every call.

SoundCraft's server is the `tools` dialect's, under its own names, `new_session`,
`open_session`, `save_session`, `batch` and `list_commands`, but for its batch, which takes its
commands as `calls`; and for its open, which says what media it misses. It renders no page
headless. What is SoundCraft's own here is how a session is read: its tracks and busses, their
comments and its markers, by `inspect_session`.
"""

import hashlib
from collections.abc import Sequence
from typing import ClassVar, override

from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppCommand, AppFailed, Inspection
from artifactr.files.craft import CRAFTS, Craft, Server, ToolsDialect
from artifactr.files.craft.project import whole
from artifactr.files.manifest import OUTLINE_LIMIT
from artifactr.files.soundcraft.project import media_type, outside, plugins


class _Clip(BaseModel):
    name: str = ""


class _Track(BaseModel):
    name: str
    kind: str = ""
    comments: str = ""
    clips: list[_Clip] = []


class _Bus(BaseModel):
    name: str


class _Marker(BaseModel):
    name: str = ""
    start: int = 0


class _Session(BaseModel):
    tracks: list[_Track] = []
    busses: list[_Bus] = []
    markers: list[_Marker] = []


class _Opened(BaseModel):
    missing: list[JsonValue] = []


class Subprocess(ToolsDialect):
    """SoundCraft's headless MCP server, spawned from its CLI on this machine for every call.

    It confines the CLI's file access to the call's own directory, but it is not a sandbox: the
    CLI runs as this process's user, with its network. A session is opened only if it is a
    `.scraft` with no audio or video, and saved as one; a blank one is an empty, untitled
    session. It renders no page headless, so a session has none. A batch runs no command of its
    engine's or app's, and names no plugin of another maker's, which SoundCraft would load.
    """

    craft: ClassVar[Craft] = CRAFTS["soundcraft"]
    extension: ClassVar[str] = ".scraft"
    new_tool: ClassVar[str] = "new_session"
    open_tool: ClassVar[str] = "open_session"
    save_tool: ClassVar[str] = "save_session"
    batch_argument: ClassVar[str] = "calls"
    list_argument: ClassVar[str] = "filter"
    denied: ClassVar[tuple[str, ...]] = ("engine.", "app.")
    """SoundCraft's engine's commands, which scan and load the machine's plugins, and the app's,
    which reach past the session."""

    @override
    def allowed(self, commands: Sequence[AppCommand]) -> None:
        """Refuse a batch that holds a denied command, or names a plugin of another maker's.

        Raises:
            AppFailed: `refused`, naming the command or the plugin.
        """
        super().allowed(commands)
        if found := next((p for c in commands for p in plugins(c.args)), None):
            raise AppFailed("refused", f"{found}: SoundCraft's adapter loads no other plugins")

    @override
    async def open(self, server: Server, source: bytes | None) -> JsonValue:
        """Open the session, or make a blank one.

        Raises:
            AppFailed: `refused` too if the bytes aren't a `.scraft`, hold audio or video, or
                name media SoundCraft can't find.
        """
        if source is None:
            return await super().open(server, source)
        whole(source, self.extension, media_type, outside)
        path = server.source(source, f"source{self.extension}")
        opened = _Opened.model_validate(await server.json(self.open_tool, path=str(path)))
        if opened.missing:
            raise AppFailed("refused", f"the session misses media: {opened.missing}")
        return None

    @override
    async def inspection(self, server: Server, document: JsonValue, content: bytes) -> Inspection:
        """The session's tracks and their clips, its busses, its tracks' comments and markers.

        It renders no page headless, so a session has no pages, as a workbook has none.

        SoundCraft stamps nothing on a save, so the fingerprint is the bytes' digest.

        Raises:
            AppFailed: `refused` if what a batch made holds audio or video.
        """
        whole(content, self.extension, media_type, outside)
        session = _Session.model_validate(await server.json("inspect_session"))
        outline = [*map(_track, session.tracks), *(f"{bus.name} (bus)" for bus in session.busses)]
        return Inspection(
            fingerprint=hashlib.sha256(content).hexdigest(),
            outline="\n".join(outline)[:OUTLINE_LIMIT],
            text="\n".join(t.comments for t in session.tracks if t.comments),
            review={"markers": [m.model_dump() for m in session.markers]},
            media_type=media_type(content),
        )


def _track(track: _Track) -> str:
    """A track's name and kind, and its clips' names."""
    clips = ", ".join(clip.name for clip in track.clips)
    return f"{track.name} ({track.kind})" + (f": {clips}" if clips else "")
