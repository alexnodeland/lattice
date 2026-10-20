# pyright: basic, reportMissingImports=false
"""The script `freecadcmd` runs for each call: the call's JSON in, its result's JSON out.

It runs in FreeCAD's own interpreter, by path, as `freecadcmd ... script.py --pass call.json`, so
it imports FreeCAD's modules and the standard library alone, nothing of lattice's. The call names
its step, `apply`, `inspect` or `render`; the source, if there is one, is `in/document.FCStd`, and
what it saves or draws goes in `out/`. It writes `result.json` beside the call: the version it ran
on, and the step's result or why it refused. Whatever else goes wrong writes no result, which the
adapter reports as a crash (native files ADR-0014).

The commands are lattice's own, carried out through FreeCAD's document API, each argument checked
by type: none runs Python, and none makes a Python feature.
"""

import json
import math
import re
import shutil
import sys
from pathlib import Path

import FreeCAD as App
import Part
import Sketcher
import TechDraw
from PIL import Image, ImageDraw

DOCUMENT = "document.FCStd"
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}")
CELL = re.compile(r"[A-Z]{1,2}[1-9][0-9]{0,4}")
PLANES = {
    "XY": App.Rotation(),
    "XZ": App.Rotation(App.Vector(1, 0, 0), 90),
    "YZ": App.Rotation(App.Vector(0, 1, 0), 90),
}
BOOLEANS = {"cut": "Part::Cut", "fuse": "Part::Fuse", "common": "Part::Common"}
CONSTRAINTS = frozenset({
    "Coincident", "Horizontal", "Vertical", "Parallel", "Perpendicular", "Equal", "Tangent",
    "Distance", "DistanceX", "DistanceY", "Radius", "Diameter", "Angle",
})  # fmt: skip
SETTABLE = frozenset({
    "App::PropertyLength", "App::PropertyDistance", "App::PropertyFloat", "App::PropertyAngle",
    "App::PropertyInteger", "App::PropertyBool", "App::PropertyString", "App::PropertyPercent",
    "App::PropertyFloatConstraint", "App::PropertyIntegerConstraint", "App::PropertyQuantity",
})  # fmt: skip
ISOMETRIC = App.Vector(1, -1, 1)
"""The direction a page looks along: FreeCAD's isometric view."""


class Refused(Exception):
    """The call is refused, with why: the adapter's `refused`."""


# ─── arguments ────────────────────────────────────────────────────────────────


def take(args, allowed, required=()):
    """The arguments, refused if one is unknown or a required one is missing."""
    if not isinstance(args, dict):
        raise Refused("args must be an object")
    if unknown := set(args) - set(allowed) - set(required):
        raise Refused(f"unknown argument {sorted(unknown)[0]}")
    if missing := [key for key in required if key not in args]:
        raise Refused(f"missing argument {missing[0]}")
    return args


def number(args, key, *, positive=False, default=None):
    """A finite number, more than 0 if `positive`."""
    value = args.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise Refused(f"{key} must be a number")
    if positive and value <= 0:
        raise Refused(f"{key} must be more than 0")
    return float(value)


def point(args, key, size, default=None):
    """A point of `size` numbers."""
    value = args.get(key, default)
    if not isinstance(value, list) or len(value) != size:
        raise Refused(f"{key} must be {size} numbers")
    return [number({key: v}, key) for v in value]


def text(args, key):
    """A string."""
    value = args.get(key)
    if not isinstance(value, str):
        raise Refused(f"{key} must be a string")
    return value


def name(args, default):
    """The name a new object asks for, or its default."""
    value = args.get("name", default)
    if not isinstance(value, str) or not NAME.fullmatch(value):
        raise Refused("name must be letters, digits and underscores, not starting with a digit")
    return value


def found(document, args, key, type_id=None):
    """The object an argument names, refused if there is none, or it is of another type."""
    obj = document.getObject(text(args, key))
    if obj is None:
        raise Refused(f"no object {args[key]}")
    if type_id is not None and obj.TypeId != type_id:
        raise Refused(f"{args[key]} is not a {type_id}")
    return obj


def at(args):
    """Where a new object stands, unrotated: the origin by default."""
    return App.Placement(App.Vector(*point(args, "at", 3, [0, 0, 0])), App.Rotation())


# ─── the commands ─────────────────────────────────────────────────────────────


def solid(type_id, fields):
    """A command that adds a primitive: its fields, each a positive number."""

    def add(document, args):
        """Add the primitive."""
        take(args, ("name", "at"), fields)
        obj = document.addObject(type_id, name(args, type_id.split("::")[1]))
        for field in fields:
            setattr(obj, field[0].upper() + field[1:], number(args, field, positive=True))
        obj.Placement = at(args)

    return add


def boolean(document, args):
    """Add the cut, fusion or common of two objects."""
    take(args, ("name",), ("operation", "base", "tool"))
    if (type_id := BOOLEANS.get(args["operation"])) is None:
        raise Refused(f"operation must be one of {sorted(BOOLEANS)}")
    obj = document.addObject(type_id, name(args, args["operation"].capitalize()))
    obj.Base, obj.Tool = found(document, args, "base"), found(document, args, "tool")


def sketch(document, args):
    """Add an empty sketch on a plane through the origin."""
    take(args, ("name", "plane"))
    if (rotation := PLANES.get(args.get("plane", "XY"))) is None:
        raise Refused(f"plane must be one of {sorted(PLANES)}")
    obj = document.addObject("Sketcher::SketchObject", name(args, "Sketch"))
    obj.Placement = App.Placement(App.Vector(), rotation)


def line(document, args):
    """Add a line to a sketch."""
    take(args, (), ("sketch", "start", "end"))
    obj = found(document, args, "sketch", "Sketcher::SketchObject")
    start, end = point(args, "start", 2), point(args, "end", 2)
    obj.addGeometry(Part.LineSegment(App.Vector(*start, 0), App.Vector(*end, 0)))


def circle(document, args):
    """Add a circle to a sketch."""
    take(args, (), ("sketch", "center", "radius"))
    obj = found(document, args, "sketch", "Sketcher::SketchObject")
    center = App.Vector(*point(args, "center", 2), 0)
    obj.addGeometry(Part.Circle(center, App.Vector(0, 0, 1), number(args, "radius", positive=True)))


def constraint(document, args):
    """Constrain a sketch's geometry."""
    take(args, (), ("sketch", "type", "values"))
    obj = found(document, args, "sketch", "Sketcher::SketchObject")
    if args["type"] not in CONSTRAINTS:
        raise Refused(f"type must be one of {sorted(CONSTRAINTS)}")
    values = args["values"]
    if not isinstance(values, list) or not 1 <= len(values) <= 6:
        raise Refused("values must be 1 to 6 numbers")
    # Geometry indices are integers, lengths and angles floats, as Sketcher takes them.
    given = [number({"values": v}, "values") for v in values]
    exact = [int(v) if isinstance(v, int) else g for v, g in zip(values, given, strict=True)]
    obj.addConstraint(Sketcher.Constraint(args["type"], *exact))


def extrude(document, args):
    """Add a solid extruded from a sketch along its normal."""
    take(args, ("name",), ("sketch", "length"))
    base = found(document, args, "sketch", "Sketcher::SketchObject")
    obj = document.addObject("Part::Extrusion", name(args, "Extrude"))
    obj.Base, obj.DirMode, obj.Solid = base, "Normal", True
    obj.LengthFwd = number(args, "length", positive=True)


def move(document, args):
    """Place an object, rotated about an axis."""
    take(args, ("axis", "angle"), ("object", "at"))
    obj = found(document, args, "object")
    axis = App.Vector(*point(args, "axis", 3, [0, 0, 1]))
    rotation = App.Rotation(axis, number(args, "angle", default=0))
    obj.Placement = App.Placement(App.Vector(*point(args, "at", 3)), rotation)


def set_property(document, args):
    """Set a property an object has, of a type that holds a plain value."""
    take(args, (), ("object", "property", "value"))
    obj, prop, value = found(document, args, "object"), text(args, "property"), args["value"]
    if prop not in obj.PropertiesList or obj.getTypeIdOfProperty(prop) not in SETTABLE:
        raise Refused(f"{obj.Name} has no property {prop} that can be set")
    if not isinstance(value, (bool, int, float, str)):
        raise Refused("value must be a number, a string or a boolean")
    setattr(obj, prop, value)


def remove(document, args):
    """Remove an object no other object uses."""
    take(args, (), ("object",))
    obj = found(document, args, "object")
    if users := [user.Name for user in obj.InList]:
        raise Refused(f"{obj.Name} is used by {', '.join(users)}")
    document.removeObject(obj.Name)


def sheet(document, args):
    """Add an empty spreadsheet."""
    take(args, ("name",))
    document.addObject("Spreadsheet::Sheet", name(args, "Spreadsheet"))


def cell(args):
    """A cell's address, such as A1."""
    if not CELL.fullmatch(where := text(args, "cell")):
        raise Refused("cell must be a column and a row, such as A1")
    return where


def sheet_set(document, args):
    """Set a cell's content."""
    take(args, (), ("sheet", "cell", "content"))
    obj = found(document, args, "sheet", "Spreadsheet::Sheet")
    obj.set(cell(args), text(args, "content"))


def sheet_alias(document, args):
    """Name a cell."""
    take(args, (), ("sheet", "cell", "alias"))
    obj = found(document, args, "sheet", "Spreadsheet::Sheet")
    if not NAME.fullmatch(alias := text(args, "alias")):
        raise Refused("alias must be letters, digits and underscores, not starting with a digit")
    obj.setAlias(cell(args), alias)


COMMANDS = {
    "box": solid("Part::Box", ("length", "width", "height")),
    "cylinder": solid("Part::Cylinder", ("radius", "height")),
    "sphere": solid("Part::Sphere", ("radius",)),
    "cone": solid("Part::Cone", ("radius1", "radius2", "height")),
    "boolean": boolean,
    "sketch": sketch,
    "sketch.line": line,
    "sketch.circle": circle,
    "sketch.constraint": constraint,
    "extrude": extrude,
    "move": move,
    "set": set_property,
    "remove": remove,
    "sheet": sheet,
    "sheet.set": sheet_set,
    "sheet.alias": sheet_alias,
}


# ─── the steps ────────────────────────────────────────────────────────────────


def opened(here, call):
    """The source, opened where it is saved, its label as it was; or a blank document."""
    source, out = here / "in" / DOCUMENT, here / "out" / DOCUMENT
    if not source.exists():
        document = App.newDocument("document")
        document.saveAs(str(out))
        return document
    shutil.copy(source, out)
    document = App.openDocument(str(out))
    if call.get("label") is not None:
        # Opening a file names its document after it; the label it was saved with is its own.
        document.Label = call["label"]
    acyclic(document)
    return document


def acyclic(document):
    """Refuse a document whose objects' links make a cycle, which FreeCAD opens regardless."""
    uses = {obj.Name: {used.Name for used in obj.OutList} for obj in document.Objects}
    users = {name: set() for name in uses}
    for name, used in uses.items():
        for each in used & users.keys():
            users[each].add(name)
    waiting = {name: len(used & users.keys()) for name, used in uses.items()}
    ready = [name for name, count in waiting.items() if count == 0]
    while ready:
        for user in users[ready.pop()]:
            waiting[user] -= 1
            if waiting[user] == 0:
                ready.append(user)
    if cycle := sorted(name for name, count in waiting.items() if count):
        raise Refused(f"its objects' links make a cycle: {', '.join(cycle)}")


def apply(document, commands):
    """Run the commands in order, refused whole at the first that fails, and recompute."""
    for index, command in enumerate(commands):
        run = COMMANDS.get(command.get("name"))
        if run is None:
            raise Refused(f"command {index + 1}: no command {command.get('name')!r}")
        try:
            run(document, command.get("args", {}))
        except Refused as refused:
            raise Refused(f"command {index + 1}, {command['name']}: {refused}") from None
        except Exception as error:
            raise Refused(f"command {index + 1}, {command['name']}: {error}") from None
    document.recompute()
    if invalid := [obj.Name for obj in document.Objects if not obj.isValid()]:
        raise Refused(f"invalid after the batch: {', '.join(invalid)}")


def reopened(document, call):
    """The document, saved, closed and opened again, so its next save is a fixpoint.

    The first save of what a batch made writes what a later open and save would change.
    """
    path = document.FileName
    document.save()
    App.closeDocument(document.Name)
    document = App.openDocument(path)
    if call.get("label") is not None:
        document.Label = call["label"]
    return document


def reading(document):
    """What the adapter reads the document into: its objects, and its sheets' cells."""
    objects = [{"name": o.Name, "label": o.Label, "type": o.TypeId} for o in document.Objects]
    cells = [
        [obj.Label, where, obj.getContents(where)]
        for obj in document.Objects
        if obj.TypeId == "Spreadsheet::Sheet"
        for where in obj.getUsedCells()
    ]
    return {"objects": objects, "cells": cells}


def draw(document, width, path):
    """Draw the shapes no other object uses, isometrically, their visible edges in black."""
    document.recompute()
    shapes = [
        obj.Shape
        for obj in document.Objects
        if not obj.InList and hasattr(obj, "Shape") and not obj.Shape.isNull()
    ]
    if not shapes:
        raise Refused("nothing to draw: no shape")
    # projectEx's first five compounds are the visible edges, the last five the hidden.
    visible = TechDraw.projectEx(Part.makeCompound(shapes), ISOMETRIC)[:5]
    edges = [edge for compound in visible for edge in compound.Edges]
    if not edges:
        raise Refused("nothing to draw: no visible edge")
    size = max(1e-9, max(e.BoundBox.DiagonalLength for e in edges))
    lines = [[(p.x, -p.y) for p in e.discretize(Deflection=size / 500)] for e in edges]
    xs = [x for points in lines for x, _ in points]
    ys = [y for points in lines for _, y in points]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1e-9)
    margin, inner = width // 20, width - 2 * (width // 20)
    height = max(16, round((max(ys) - min(ys)) / span * inner) + 2 * margin)
    image = Image.new("RGB", (width, height), "white")
    pen = ImageDraw.Draw(image)
    for points in lines:
        scaled = [
            (margin + (x - min(xs)) / span * inner, margin + (y - min(ys)) / span * inner)
            for x, y in points
        ]
        pen.line(scaled, fill="black", width=1)
    image.save(path, "PNG")


def step(here, call):
    """The call's step, on the source or a blank document."""
    try:
        document = opened(here, call)
    except Refused:
        raise
    except Exception as error:
        raise Refused(f"FreeCAD can't open it: {error}") from None
    if call["step"] == "render":
        if call["page"] != 1:
            raise Refused(f"no page {call['page']}: a model is drawn as page 1")
        draw(document, call["width"], here / "out" / "page.png")
        return {}
    if call["step"] == "apply":
        if call["commands"]:
            apply(document, call["commands"])
            document = reopened(document, call)
        document.save()
    return reading(document)


def main():
    """Run the call, and write its result beside it."""
    called = Path(sys.argv[sys.argv.index("--pass") + 1])
    here = called.parent
    # No backup beside a save, no state between calls.
    App.ParamGet("User parameter:BaseApp/Preferences/Document").SetBool("CreateBackupFiles", False)
    version = ".".join(App.Version()[:3])
    try:
        result = {"version": version, "result": step(here, json.loads(called.read_text()))}
    except Refused as refused:
        result = {"version": version, "refused": str(refused)}
    (here / "result.json").write_text(json.dumps(result))


main()
