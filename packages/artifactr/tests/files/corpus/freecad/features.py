"""Each feature of an `.FCStd`, read out of its `Document.xml` into a value two saves compare by.

A value keeps what the feature means: each object's type, its dimensions, its placement, its
links, a sketch's geometry and constraints, a sheet's cells and the expressions that bind them.
It leaves out what FreeCAD derives or stamps: the shapes, which a recompute makes again, ids, and
the dates (lattice RFC-0003, phase 2).
"""

import io
import zipfile
from collections.abc import Callable
from typing import Final
from xml.etree import ElementTree

Value = list[tuple[object, ...]]
Element = ElementTree.Element

PLACES: Final = 6
"""The decimals a number is compared to."""

DIMENSIONS: Final = ("Length", "Width", "Height", "Radius", "Radius1", "Radius2", "LengthFwd")
PLACEMENT: Final = ("Px", "Py", "Pz", "Q0", "Q1", "Q2", "Q3")
CONSTRAINT: Final = ("Type", "Value", "First", "FirstPos", "Second", "SecondPos")


class Model:
    """A document's objects, in order, and each object's properties by name."""

    def __init__(self, content: bytes) -> None:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.root = ElementTree.fromstring(archive.read("Document.xml"))
            names = archive.namelist()
            self.gui = (
                ElementTree.fromstring(archive.read("GuiDocument.xml"))
                if "GuiDocument.xml" in names
                else None
            )
        self.types = {
            o.get("name", ""): o.get("type", "") for o in self.root.iter("Object") if o.get("type")
        }
        data = self.root.find("ObjectData")
        self.data = {
            o.get("name", ""): {p.get("name", ""): p for p in o.iter("Property")}
            for o in ([] if data is None else data)
        }

    def value(self, name: str, prop: str) -> Element | None:
        """The element that holds an object's property's value."""
        held = self.data[name].get(prop)
        return None if held is None else next(iter(held), None)


def number(value: str | None) -> float:
    return round(float(value or 0), PLACES)


def dimensions(model: Model, name: str) -> tuple[object, ...]:
    found = [
        (d, number(e.get("value"))) for d in DIMENSIONS if (e := model.value(name, d)) is not None
    ]
    return tuple(found)


def place(model: Model, name: str) -> tuple[float, ...]:
    held = model.value(name, "Placement")
    return tuple(number(None if held is None else held.get(key)) for key in PLACEMENT)


def link(model: Model, name: str, prop: str) -> str | None:
    held = model.value(name, prop)
    return None if held is None else held.get("value")


def primitives(model: Model) -> Value:
    """Each object's type, dimensions and placement."""
    return [
        (name, kind, dimensions(model, name), place(model, name))
        for name, kind in model.types.items()
    ]


def booleans(model: Model) -> Value:
    """Each object's type, and what each boolean cuts or fuses."""
    return [
        (name, kind, link(model, name, "Base"), link(model, name, "Tool"))
        for name, kind in model.types.items()
    ]


def sketch(model: Model) -> Value:
    """Each sketch's geometry, its type and its points, then its constraints."""
    found: Value = []
    for name, kind in model.types.items():
        if kind != "Sketcher::SketchObject":
            continue
        for geometry in model.data[name]["Geometry"].iter("Geometry"):
            shape = next(
                child for child in geometry if child.tag not in {"GeoExtensions", "Construction"}
            )
            found.append(
                (name, shape.tag, tuple(sorted((k, number(v)) for k, v in shape.attrib.items())))
            )
        for constraint in model.data[name]["Constraints"].iter("Constrain"):
            found.append((name, *(number(constraint.get(key)) for key in CONSTRAINT)))
    return found


def extrusion(model: Model) -> Value:
    """The sketch, and the solid extruded from it: its base, its length and whether it is solid."""
    found = sketch(model)
    for name, kind in model.types.items():
        if kind == "Part::Extrusion":
            solid = model.value(name, "Solid")
            found.append(
                (
                    name,
                    link(model, name, "Base"),
                    dimensions(model, name),
                    solid.get("value") if solid is not None else None,
                )
            )
    return found


def part_design(model: Model) -> Value:
    """The body's objects, the pad's profile and length."""
    found: Value = [(name, kind) for name, kind in model.types.items()]
    for name, kind in model.types.items():
        if kind == "PartDesign::Pad":
            profile = model.value(name, "Profile")
            found.append(
                (name, None if profile is None else profile.get("value"), dimensions(model, name))
            )
    return found


def cells(model: Model) -> Value:
    return [
        (name, cell.get("address"), cell.get("content"), cell.get("alias"))
        for name, kind in model.types.items()
        if kind == "Spreadsheet::Sheet"
        for cell in model.data[name]["cells"].iter("Cell")
    ]


def expressions(model: Model) -> Value:
    """The cells, and each object's expressions, by the property each binds."""
    bound = [
        (name, expression.get("path"), expression.get("expression"))
        for name in model.types
        if "ExpressionEngine" in model.data[name]
        for expression in model.data[name]["ExpressionEngine"].iter("Expression")
    ]
    return [*cells(model), *bound]


def placement(model: Model) -> Value:
    return [(name, place(model, name)) for name in model.types]


def gui(model: Model) -> Value:
    """Each object's label, and each view provider's visibility, which the GUI's part holds."""
    labels = [(name, link(model, name, "Label")) for name in model.types]
    providers = [] if model.gui is None else model.gui.iter("ViewProvider")
    shown = [(p.get("name"), next(p.iter("Bool")).get("value")) for p in providers]
    return [*labels, *shown]


READERS: Final[dict[str, Callable[[Model], Value]]] = {
    "primitives": primitives,
    "booleans": booleans,
    "sketch": sketch,
    "extrusion": extrusion,
    "part_design": part_design,
    "spreadsheet": cells,
    "expressions": expressions,
    "placement": placement,
    "gui": gui,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a document."""
    return READERS[feature](Model(content))
