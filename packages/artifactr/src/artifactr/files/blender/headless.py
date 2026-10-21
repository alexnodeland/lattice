"""Blender run headless on this machine: `blender --background` running the adapter's script.

Blender has no server of its own, so each call is a [`Script`][artifactr.files.craft.Script]: the
call as JSON, which `script.py` carries out through Blender's data API, and its result read back
(native files ADR-0015). A file is scanned before Blender is given it, and refused if it holds
anything that may run Python or read another file. Its script confines nothing, so the adapter is
made only with `trusted=True`.
"""

import math
import threading
import time
from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Final

import anyio
import anyio.to_thread
from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppCommand, AppFailed, Applied, CommandSpec, Inspection, Talk
from artifactr.files.blender.document import LIMIT, Scanned, fingerprint, scan
from artifactr.files.craft import CRAFTS, FOUND, PREVIEW, Craft, Script
from artifactr.files.manifest import BLEND, OUTLINE_LIMIT

SCRIPT: Final = Path(__file__).parent / "console" / "script.py"
"""The script Blender runs: in a folder that isn't a package, since it imports only in Blender,
and nothing that imports every module of artifactr must reach it."""

SAVED: Final = "document.blend"
"""What the script saves a file as, in `out/`."""

BATCH: Final = 200
"""The most commands a batch may hold."""

WIDEST: Final = 4096
"""The widest a page may be drawn, in pixels."""

ARGUMENTS: Final = (
    "--background",
    "--factory-startup",
    "--disable-autoexec",
    "--offline-mode",
    "-noaudio",
    "--python-exit-code",
    "1",
    "--python",
)
"""No window, no settings or startup file of the user's, no script a file holds run, no network
and no sound; and a crash for a script that raises."""

COMMANDS: Final = (
    CommandSpec(
        name="cube",
        signature="{size, name?, at?: [x, y, z]}",
        description="Add a cube, its size in metres, as a mesh object of its own.",
    ),
    CommandSpec(
        name="sphere",
        signature="{radius, name?, at?: [x, y, z]}",
        description="Add a UV sphere.",
    ),
    CommandSpec(
        name="cylinder",
        signature="{radius, depth, name?, at?: [x, y, z]}",
        description="Add a cylinder, standing along Z.",
    ),
    CommandSpec(
        name="cone",
        signature="{radius1, radius2, depth, name?, at?: [x, y, z]}",
        description="Add a cone, or a frustum, its base radius1 and its top radius2.",
    ),
    CommandSpec(
        name="plane",
        signature="{size, name?, at?: [x, y, z]}",
        description="Add a square plane, flat on XY.",
    ),
    CommandSpec(
        name="move",
        signature="{object, at?: [x, y, z], rotation?: [x, y, z], scale?: [x, y, z]}",
        description="Place an object, rotate it by degrees about X, Y and Z, and scale it.",
    ),
    CommandSpec(
        name="material",
        signature="{name?, color?: [r, g, b], metallic?, roughness?}",
        description="Add a material: its colour and how metallic and how rough, each 0 to 1.",
    ),
    CommandSpec(
        name="assign",
        signature="{object, material}",
        description="Give a mesh object a material, in its first slot.",
    ),
    CommandSpec(
        name="modifier",
        signature="{object, type, name?, ...}",
        description=(
            "Add a modifier to a mesh object: subdivision {levels}, bevel {width, segments}, "
            "array {count}, mirror {axes: [x, y, z] booleans} or solidify {thickness}."
        ),
    ),
    CommandSpec(
        name="camera",
        signature="{at: [x, y, z], look_at?: [x, y, z], lens?, name?}",
        description=(
            "Add a camera looking at a point, the origin by default, its lens in millimetres; "
            "the scene's camera unless it has one."
        ),
    ),
    CommandSpec(
        name="light",
        signature="{type: point | sun | spot | area, energy, at: [x, y, z], look_at?, color?}",
        description="Add a light, its power in watts (a sun's in watts per square metre).",
    ),
    CommandSpec(
        name="collection",
        signature="{name, parent?}",
        description="Add a collection, in the scene's own or in another.",
    ),
    CommandSpec(
        name="link",
        signature="{object, collection}",
        description="Move an object into a collection, out of every other.",
    ),
    CommandSpec(
        name="render",
        signature="{engine?: workbench | cycles, width?, height?, samples?}",
        description="Set how the scene renders: its engine, its size in pixels, Cycles' samples.",
    ),
    CommandSpec(
        name="set",
        signature="{object, property: name | hide_render | hide_viewport, value}",
        description="Rename an object, or set whether it is rendered or shown.",
    ),
    CommandSpec(
        name="remove",
        signature="{object}",
        description="Remove an object that is no other object's parent.",
    ),
)
"""The commands an agent may run: lattice's own, none of them Python."""


SCANNING: Final = threading.Lock()
"""Held by the one scan running in this process."""


def _scanned(source: bytes, limit: int, until: float) -> Scanned:
    """A scan, once no other is running, refused as a timeout past `until`."""
    if not SCANNING.acquire(timeout=max(0.0, until - time.monotonic())):
        raise AppFailed("timeout", "another scan ran past this one's deadline")
    try:
        return scan(source, limit, until=until)
    finally:
        SCANNING.release()


class _Object(BaseModel):
    name: str
    type: str
    collections: list[str]


class _Reading(BaseModel):
    objects: list[_Object] = []
    materials: list[str] = []
    collections: list[str] = []


class Subprocess:
    """Blender, `blender --background`, started on the adapter's script for every call.

    A blank file is Blender's empty factory scene, saved compressed, as its GUI saves by default;
    a file keeps whether it came compressed.

    Its script reads and writes wherever this process's user can, so it is made only with
    `trusted=True`, for trusted files or a process already confined, such as the worker.

    Args:
        cli: `blender`.
        version: The version it must be, which provenance records.
        trusted: Whether its files are trusted, or this process confined: required.
        limit: The most bytes a file may hold, saved or inflated: 128 MiB by default.
        launcher: The command the CLI is started under; none by default.

    Raises:
        ValueError: If `trusted` isn't given.
    """

    craft: ClassVar[Craft] = CRAFTS["blender"]
    extension: ClassVar[str] = ".blend"
    build: str | None = None
    talk: Talk = "save"

    def __init__(
        self,
        cli: str | Path,
        *,
        version: str,
        trusted: bool = False,
        limit: int = LIMIT,
        launcher: Sequence[str] = (),
    ) -> None:
        self.version: str = version
        self.limit = limit
        self._script = Script(
            self.craft,
            cli,
            SCRIPT,
            version=version,
            arguments=ARGUMENTS,
            ending=("--",),
            trusted=trusted,
            limit=limit,
            launcher=launcher,
        )

    @property
    def name(self) -> str:
        """The app's name, which provenance records."""
        return self.craft.name

    @property
    def integration(self) -> str:
        """The key that switches it in a workspace, `files:blender`."""
        return self.craft.key

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Applied:
        """Run a batch of commands on a file, or a blank one, and save it.

        The batch stops at the first command that fails, which refuses it whole.
        """
        if len(commands) > BATCH:
            raise AppFailed("refused", f"a batch holds at most {BATCH} commands")
        scanned, deadline = (
            (None, deadline) if source is None else await self._scan(source, deadline)
        )
        call: dict[str, JsonValue] = {
            "step": "apply",
            "compressed": True if scanned is None else scanned.compressed,
            "commands": [command.model_dump(mode="json") for command in commands],
        }
        given = None if scanned is None else scanned.content
        ran = await self._script.run(deadline, call, given, self.extension, wanted={SAVED})
        if (saved := ran.files.get(SAVED)) is None:
            raise AppFailed("crashed", "Blender saved no file")
        return Applied(content=saved, inspection=await self._inspection(saved, ran.result))

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        """Read a file's objects, materials and collections, and its fingerprint."""
        scanned, deadline = await self._scan(source, deadline)
        ran = await self._script.run(deadline, {"step": "inspect"}, scanned.content, self.extension)
        return await self._inspection(source, ran.result)

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        """Draw the scene through its camera, by Workbench, `PREVIEW` times `scale` wide, as page 1.

        Raises:
            AppFailed: `refused` too for any page but the first, a scale that isn't a positive
                number, or a scene with no camera.
        """
        if page != 1:
            raise AppFailed("refused", f"no page {page}: a scene is drawn as page 1")
        if not math.isfinite(scale) or scale <= 0:
            raise AppFailed("refused", f"a scale must be a positive number, not {scale}")
        scanned, deadline = await self._scan(source, deadline)
        call: dict[str, JsonValue] = {
            "step": "render",
            "page": page,
            "width": min(WIDEST, max(16, round(PREVIEW * scale))),
        }
        ran = await self._script.run(
            deadline, call, scanned.content, self.extension, wanted={"page.png"}
        )
        if (png := ran.files.get("page.png")) is None:
            raise AppFailed("crashed", "Blender drew no page")
        return png

    async def commands(self, query: str) -> Sequence[CommandSpec]:
        """The commands whose name or description mentions the query: no CLI is started."""
        asked = query.casefold()
        found = [c for c in COMMANDS if asked in f"{c.name} {c.description}".casefold()]
        return found[:FOUND]

    async def _scan(self, source: bytes, deadline: float) -> tuple[Scanned, float]:
        """The source, scanned in a thread, and what is left of the call's deadline.

        The scan looks at the deadline as it goes and stops itself past it, so the call waits for
        its thread, which never outlives the call by more than a moment; and one scan runs at a
        time in this process, so none overlaps another.

        Raises:
            AppFailed: `timeout` past the deadline, and whatever the scan refuses.
        """
        until = time.monotonic() + deadline
        scanned = await anyio.to_thread.run_sync(_scanned, source, self.limit, until)
        return scanned, until - time.monotonic()

    async def _inspection(self, content: bytes, result: JsonValue) -> Inspection:
        """The objects as the outline, a line each, with the collections they are in."""
        reading = _Reading.model_validate(result)
        outline = "\n".join(
            f"{o.name} ({o.type}" + "".join(f", in {c}" for c in o.collections) + ")"
            for o in reading.objects
        )
        return Inspection(
            fingerprint=await anyio.to_thread.run_sync(fingerprint, content, self.limit),
            outline=outline[:OUTLINE_LIMIT],
            text="\n".join(f"Material: {m}" for m in reading.materials),
            pages=1,
            media_type=BLEND,
        )
