"""The pure part of the script `freecadcmd` runs: its arguments' checks, and a cycle's refusal.

The script imports FreeCAD's modules, which no pull request has, so it is imported here with
stand-ins for them, under a name that doesn't run it; `test_live.py` runs it in FreeCAD itself.
"""

import importlib.util
import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from artifactr.files.freecad.headless import SCRIPT

FREECADS = ("FreeCAD", "Part", "Sketcher", "TechDraw", "PIL")


@pytest.fixture(scope="module")
def console() -> Iterator[Any]:
    stand_ins = {name: mock.MagicMock(name=name) for name in FREECADS}
    with mock.patch.dict(sys.modules, stand_ins):
        spec = importlib.util.spec_from_file_location("freecad_console", SCRIPT)
        assert spec
        assert spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module


def test_arguments_are_taken_only_as_named(console: ModuleType) -> None:
    assert console.take({"b": 1}, ("a",), ("b",)) == {"b": 1}
    for args, why in (
        ([], "args must be an object"),
        ({"c": 1, "b": 1}, "unknown argument c"),
        ({}, "missing argument b"),
    ):
        with pytest.raises(console.Refused, match=why):
            console.take(args, ("a",), ("b",))


@pytest.mark.parametrize("value", [True, "1", None, float("inf"), float("nan")])
def test_a_number_is_a_finite_number_and_no_boolean(console: ModuleType, value: object) -> None:
    with pytest.raises(console.Refused, match="must be a number"):
        console.number({"x": value}, "x")


def test_numbers_points_names_cells_and_texts(console: ModuleType) -> None:
    assert console.number({"x": 2}, "x", positive=True) == 2.0
    assert console.number({}, "x", default=0) == 0.0
    with pytest.raises(console.Refused, match="more than 0"):
        console.number({"x": 0}, "x", positive=True)
    assert console.point({"p": [1, 2]}, "p", 2) == [1.0, 2.0]
    with pytest.raises(console.Refused, match="must be 3 numbers"):
        console.point({"p": [1, 2]}, "p", 3)
    assert console.name({}, "Box") == "Box"
    for bad in ("1Box", "a b", "x" * 65, 3):
        with pytest.raises(console.Refused, match="name must be"):
            console.name({"name": bad}, "Box")
    assert console.cell({"cell": "AB12"}) == "AB12"
    for bad in ("A0", "a1", "ABC1", "A1;B2"):
        with pytest.raises(console.Refused, match="cell must be"):
            console.cell({"cell": bad})
    with pytest.raises(console.Refused, match="must be a string"):
        console.text({"t": 1}, "t")


def test_a_cell_cant_refer_to_another_document(console: ModuleType) -> None:
    sheet = SimpleNamespace(TypeId="Spreadsheet::Sheet", set=mock.Mock())
    document = SimpleNamespace(getObject=lambda _: sheet)
    with pytest.raises(console.Refused, match="another document"):
        console.sheet_set(document, {"sheet": "S", "cell": "A1", "content": "=o#Box.Length"})
    sheet.set.assert_not_called()


def model(**uses: str) -> SimpleNamespace:
    """A document whose objects each use the objects named in their value, by OutList."""
    objects = {name: SimpleNamespace(Name=name, OutList=[]) for name in uses}
    for name, used in uses.items():
        objects[name].OutList = [objects[each] for each in used.split()]
    return SimpleNamespace(Objects=list(objects.values()))


def test_a_cycle_is_refused_and_a_chain_isnt(console: ModuleType) -> None:
    console.acyclic(model(Box="", Cut="Box Hole", Hole="", Fusion="Cut"))
    with pytest.raises(console.Refused, match="cycle: Cut, Fusion"):
        console.acyclic(model(Box="", Cut="Fusion", Fusion="Cut", Sphere="Box"))
