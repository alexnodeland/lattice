"""FreeCAD run headless on this machine: `freecadcmd` running the adapter's script for every call.

FreeCAD has no server, so each call is a [`Script`][artifactr.files.craft.Script]: the
call as JSON, which `script.py` carries out through FreeCAD's document API, and its result read
back (native files ADR-0014). A document is scanned before FreeCAD is given it, and refused if it
holds anything that would run Python. Its script confines nothing, so the adapter is made only
with `trusted=True`.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import ClassVar, Final

from pydantic import BaseModel, JsonValue

from artifactr.files.app import AppCommand, AppFailed, Applied, CommandSpec, Inspection, Talk
from artifactr.files.craft import CRAFTS, FOUND, PREVIEW, Craft, Script
from artifactr.files.freecad.document import fingerprint, scan, with_gui
from artifactr.files.manifest import FCSTD, OUTLINE_LIMIT

SCRIPT: Final = Path(__file__).parent / "console" / "script.py"
"""The script `freecadcmd` runs: in a folder that isn't a package, since it imports only in
FreeCAD, and nothing that imports every module of artifactr must reach it."""

SAVED: Final = "document.FCStd"
"""What the script saves a document as, in `out/`."""

ARGUMENTS: Final = ("-u", "user.cfg", "-s", "system.cfg", "--safe-mode")
"""Its settings in the call's directory, and no user macro, addon or setting of its own."""

COMMANDS: Final = (
    CommandSpec(
        name="box",
        signature="{length, width, height, name?, at?: [x, y, z]}",
        description="Add a box, its sizes in millimetres.",
    ),
    CommandSpec(
        name="cylinder",
        signature="{radius, height, name?, at?: [x, y, z]}",
        description="Add a cylinder, standing on the XY plane.",
    ),
    CommandSpec(
        name="sphere",
        signature="{radius, name?, at?: [x, y, z]}",
        description="Add a sphere.",
    ),
    CommandSpec(
        name="cone",
        signature="{radius1, radius2, height, name?, at?: [x, y, z]}",
        description="Add a cone, or a frustum, its base radius1 and its top radius2.",
    ),
    CommandSpec(
        name="boolean",
        signature="{operation: cut | fuse | common, base, tool, name?}",
        description="Add the cut, fusion or common of two objects.",
    ),
    CommandSpec(
        name="sketch",
        signature="{plane?: XY | XZ | YZ, name?}",
        description="Add an empty sketch on a plane through the origin, XY by default.",
    ),
    CommandSpec(
        name="sketch.line",
        signature="{sketch, start: [x, y], end: [x, y]}",
        description="Add a line to a sketch, in its plane's coordinates.",
    ),
    CommandSpec(
        name="sketch.circle",
        signature="{sketch, center: [x, y], radius}",
        description="Add a circle to a sketch.",
    ),
    CommandSpec(
        name="sketch.constraint",
        signature="{sketch, type, values: [...]}",
        description=(
            "Constrain a sketch's geometry, by Sketcher's constraint type (Coincident, "
            "Horizontal, Vertical, Parallel, Perpendicular, Equal, Tangent, Distance, "
            "DistanceX, DistanceY, Radius, Diameter, Angle) and its values: geometry and "
            "vertex indices as integers, then a length or an angle."
        ),
    ),
    CommandSpec(
        name="extrude",
        signature="{sketch, length, name?}",
        description="Add a solid extruded from a closed sketch, along its normal.",
    ),
    CommandSpec(
        name="move",
        signature="{object, at: [x, y, z], axis?: [x, y, z], angle?}",
        description="Place an object at a point, rotated by an angle in degrees about an axis.",
    ),
    CommandSpec(
        name="set",
        signature="{object, property, value}",
        description=(
            "Set an object's number, length, angle, boolean or string property, such as a "
            "box's Length or any object's Label."
        ),
    ),
    CommandSpec(
        name="remove",
        signature="{object}",
        description="Remove an object that no other object uses.",
    ),
    CommandSpec(
        name="sheet",
        signature="{name?}",
        description="Add an empty spreadsheet.",
    ),
    CommandSpec(
        name="sheet.set",
        signature="{sheet, cell, content}",
        description="Set a cell, such as A1, to a value, or a formula that starts with =.",
    ),
    CommandSpec(
        name="sheet.alias",
        signature="{sheet, cell, alias}",
        description="Name a cell, so expressions can use it as Sheet.alias.",
    ),
)
"""The commands an agent may run: lattice's own, none of them Python."""


class _Object(BaseModel):
    name: str
    label: str
    type: str


class _Reading(BaseModel):
    objects: list[_Object] = []
    cells: list[tuple[str, str, str]] = []


class Subprocess:
    """FreeCAD's console, `freecadcmd`, started on the adapter's script for every call.

    A blank document is FreeCAD's new one. A document's `GuiDocument.xml`, which the console
    drops, is put back in what it saves; its thumbnail isn't.

    Its script reads and writes wherever this process's user can, so it is made only with
    `trusted=True`, for trusted files or a process already confined, such as the worker.

    Args:
        cli: `freecadcmd`.
        version: The version it must be, which provenance records.
        trusted: Whether its files are trusted, or this process confined: required.
        limit: The most bytes a document may hold, saved or inflated: 256 MiB by default.
        launcher: The command the CLI is started under; none by default.

    Raises:
        ValueError: If `trusted` isn't given.
    """

    craft: ClassVar[Craft] = CRAFTS["freecad"]
    extension: ClassVar[str] = ".FCStd"
    build: str | None = None
    talk: Talk = "save"

    def __init__(
        self,
        cli: str | Path,
        *,
        version: str,
        trusted: bool = False,
        limit: int = 256 << 20,
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
        """The key that switches it in a workspace, `files:freecad`."""
        return self.craft.key

    async def apply(
        self, source: bytes | None, commands: Sequence[AppCommand], *, deadline: float
    ) -> Applied:
        """Run a batch of commands on a document, or a blank one, recompute it, and save it.

        The batch stops at the first command that fails, which refuses it whole, as does an
        object it leaves invalid. With no commands, nothing is recomputed, so the shapes'
        bytes are kept.
        """
        scanned = None if source is None else scan(source, self.limit)
        call: dict[str, JsonValue] = {
            "step": "apply",
            "label": None if scanned is None else scanned.label,
            "commands": [command.model_dump(mode="json") for command in commands],
        }
        given = None if scanned is None else scanned.content
        ran = await self._script.run(deadline, call, given, self.extension, wanted={SAVED})
        if (saved := ran.files.get(SAVED)) is None:
            raise AppFailed("crashed", "freecadcmd saved no document")
        content = with_gui(saved, given)
        return Applied(content=content, inspection=_inspection(content, ran.result))

    async def inspect(self, source: bytes, *, deadline: float) -> Inspection:
        """Read a document's objects, its sheets' cells, and its fingerprint."""
        scanned = scan(source, self.limit)
        call: dict[str, JsonValue] = {"step": "inspect", "label": scanned.label}
        ran = await self._script.run(deadline, call, scanned.content, self.extension)
        return _inspection(scanned.content, ran.result)

    async def render(self, source: bytes, page: int, *, scale: float, deadline: float) -> bytes:
        """Draw the model's visible edges, isometrically, `PREVIEW` times `scale` wide, as page 1.

        Raises:
            AppFailed: `refused` too for any page but the first, or a model with no shape.
        """
        if page != 1:
            raise AppFailed("refused", f"no page {page}: a model is drawn as page 1")
        scanned = scan(source, self.limit)
        call: dict[str, JsonValue] = {
            "step": "render",
            "label": scanned.label,
            "page": page,
            "width": max(16, round(PREVIEW * scale)),
        }
        ran = await self._script.run(
            deadline, call, scanned.content, self.extension, wanted={"page.png"}
        )
        if (png := ran.files.get("page.png")) is None:
            raise AppFailed("crashed", "freecadcmd drew no page")
        return png

    async def commands(self, query: str) -> Sequence[CommandSpec]:
        """The commands whose name or description mentions the query: no CLI is started."""
        asked = query.casefold()
        found = [c for c in COMMANDS if asked in f"{c.name} {c.description}".casefold()]
        return found[:FOUND]


def _inspection(content: bytes, result: JsonValue) -> Inspection:
    """The objects as the outline, a line each, and the sheets' cells as the text."""
    reading = _Reading.model_validate(result)
    outline = "\n".join(f"{o.label} ({o.type})" for o in reading.objects)
    return Inspection(
        fingerprint=fingerprint(content),
        outline=outline[:OUTLINE_LIMIT],
        text="\n".join(f"{sheet}.{cell}: {value}" for sheet, cell, value in reading.cells),
        pages=1,
        media_type=FCSTD,
    )
