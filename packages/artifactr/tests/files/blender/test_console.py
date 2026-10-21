"""The pure part of the script Blender runs: its arguments' checks, and what it refuses itself.

The script imports Blender's modules, which no pull request has, so it is imported here with
stand-ins for them, under a name that doesn't run it; `test_live.py` runs it in Blender itself.
"""

import ast
import importlib.util
import sys
from collections.abc import Iterator
from types import ModuleType, SimpleNamespace
from typing import Any
from unittest import mock

import pytest

from artifactr.files.blender.headless import SCRIPT

BLENDERS = ("bpy", "bmesh", "mathutils")


@pytest.fixture(scope="module")
def console() -> Iterator[Any]:
    stand_ins = {name: mock.MagicMock(name=name) for name in BLENDERS}
    with mock.patch.dict(sys.modules, stand_ins):
        spec = importlib.util.spec_from_file_location("blender_console", SCRIPT)
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


def test_numbers_wholes_points_names_and_texts_are_bounded(console: ModuleType) -> None:
    assert console.number({"x": 2}, "x", low=1) == 2.0
    assert console.number({}, "x", default=0) == 0.0
    with pytest.raises(console.Refused, match="from 1 to 5"):
        console.number({"x": 9}, "x", low=1, high=5)
    assert console.whole({"n": 3}, "n", low=1, high=4) == 3
    for bad in (5, 2.0, True):
        with pytest.raises(console.Refused, match="whole number from 1 to 4"):
            console.whole({"n": bad}, "n", low=1, high=4)
    assert console.point({"p": [1, 2, 3]}, "p") == [1.0, 2.0, 3.0]
    with pytest.raises(console.Refused, match="must be 3 numbers"):
        console.point({"p": [1, 2]}, "p")
    assert console.name({}, "Cube") == "Cube"
    for bad in ("1Cube", "a b", "x" * 64, 3, "../x"):
        with pytest.raises(console.Refused, match="name must be"):
            console.name({"name": bad}, "Cube")
    with pytest.raises(console.Refused, match="must be a string"):
        console.text({"t": 1}, "t")


def test_a_modifier_is_one_of_the_allowed_types(console: ModuleType) -> None:
    for args in ({"object": "Cube", "type": "nodes"}, [], {"object": "Cube"}):
        with pytest.raises(console.Refused, match="type must be one of"):
            console.modifier(args)


def test_only_a_name_or_a_visibility_is_set(console: ModuleType) -> None:
    obj = SimpleNamespace(name="Cube")
    console.bpy.data.objects = {"Cube": obj}
    for prop, value, why in (
        ("location", [0, 0, 0], "property must be one of"),
        ("hide_render", "yes", "hide_render must be a bool"),
        ("name", "a b", "name must be a str, a name"),
    ):
        with pytest.raises(console.Refused, match=why):
            console.set_property({"object": "Cube", "property": prop, "value": value})
    console.set_property({"object": "Cube", "property": "name", "value": "Box"})
    assert obj.name == "Box"


def test_a_cycle_of_parents_and_whatever_the_scan_refuses_are_refused_again(
    console: ModuleType,
) -> None:
    data = console.bpy.data
    for kind in console.collections():
        setattr(data, kind, [])
    objects = {
        n: SimpleNamespace(name=n, parent=None, animation_data=None, type="EMPTY") for n in "abc"
    }
    objects["b"].parent = objects["a"]
    data.objects = list(objects.values())
    console.inert()
    objects["a"].parent = objects["c"]
    objects["c"].parent = objects["b"]
    with pytest.raises(console.Refused, match="parents make a cycle"):
        console.inert()
    objects["a"].parent = None
    objects["b"].animation_data = object()
    with pytest.raises(console.Refused, match="animation or a driver"):
        console.inert()
    data.texts = ["run.py"]
    with pytest.raises(console.Refused, match="aren't allowed: texts"):
        console.inert()


def test_a_command_is_dispatched_and_what_blender_raises_is_a_refusal(
    console: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_: object) -> None:
        raise OverflowError("Python int too large to convert to C int")

    monkeypatch.setitem(console.COMMANDS, "cube", broken)
    for commands, why in (
        ([{"name": "nope"}], "command 1: no command 'nope'"),
        ([{"name": "cube", "args": {}}], "command 1, cube: Python int too large"),
        ([{"name": "remove", "args": []}], "command 1, remove: args must be an object"),
    ):
        with pytest.raises(console.Refused, match=why):
            console.apply(commands)


def test_a_modifiers_numbers_and_a_lights_are_bounded(console: ModuleType) -> None:
    added = SimpleNamespace()
    console.subdivision(added, {"levels": 4})
    assert (added.levels, added.render_levels) == (4, 4)
    for setting, args, why in (
        (console.subdivision, {"levels": 5}, "levels must be a whole number from 0 to 4"),
        (console.bevel, {"segments": 17}, "segments must be a whole number from 1 to 16"),
        (console.array, {"count": 1001}, "count must be a whole number from 1 to 1000"),
        (console.mirror, {"axes": [True]}, "axes must be 3 booleans"),
        (console.solidify, {"thickness": "1"}, "thickness must be a number"),
    ):
        with pytest.raises(console.Refused, match=why):
            setting(SimpleNamespace(), args)
    with pytest.raises(console.Refused, match="type must be one of"):
        console.light({"type": "laser", "energy": 1, "at": [0, 0, 0]})


def modifier(kind: str, **settings: object) -> SimpleNamespace:
    return SimpleNamespace(type=kind, **settings)


def test_an_objects_modifiers_are_bounded_once_opened(console: ModuleType) -> None:
    def mesh(*modifiers: SimpleNamespace) -> SimpleNamespace:
        return SimpleNamespace(name="Cube", modifiers=list(modifiers))

    console.bounded(mesh(modifier("ARRAY", fit_type="FIXED_COUNT", count=10)))
    for given, why in (
        ([modifier("MIRROR")] * 9, "more than 8 modifiers"),
        ([modifier("ARRAY", fit_type="FIT_LENGTH", count=1)], "to a length or a curve"),
        ([modifier("ARRAY", fit_type="FIXED_COUNT", count=40)] * 2, "1600 copies"),
        ([modifier("SUBSURF", levels=1, render_levels=6)], "more than 4 levels"),
        ([modifier("BEVEL", segments=100)], "more than 16 segments"),
    ):
        with pytest.raises(console.Refused, match=why):
            console.bounded(mesh(*given))


def test_a_light_or_a_camera_is_aimed_and_not_at_itself(
    console: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(console, "Vector", Point)
    obj = SimpleNamespace(location=Point([1, 1, 1]))
    with pytest.raises(console.Refused, match="look_at must differ from at"):
        console.aimed(obj, {"look_at": [1, 1, 1]})


class Point:
    """A stand-in for Blender's vector: subtraction and a length."""

    def __init__(self, values: list[float]) -> None:
        self.values = values

    def __sub__(self, other: "Point") -> "Point":
        return Point([a - b for a, b in zip(self.values, other.values, strict=True)])

    @property
    def length(self) -> float:
        return sum(a * a for a in self.values) ** 0.5


def test_what_blender_opened_holds_only_the_data_blocks_the_scan_allows(
    console: ModuleType,
) -> None:
    data = console.bpy.data
    for kind in console.collections():
        setattr(data, kind, [])
    data.objects = [SimpleNamespace(name="a", parent=None, animation_data=None, type="EMPTY")]
    console.inert()
    data.node_groups = ["Group"]
    with pytest.raises(console.Refused, match="aren't allowed: node_groups"):
        console.inert()
    data.node_groups = []
    data.materials = [
        SimpleNamespace(animation_data=None, node_tree=SimpleNamespace(animation_data=1))
    ]
    with pytest.raises(console.Refused, match="animation or a driver"):
        console.inert()


ALLOWED_OPS = {
    ("wm", "open_mainfile"),
    ("wm", "save_as_mainfile"),
    ("wm", "read_factory_settings"),
    ("render", "render"),
}


def test_the_script_runs_no_code_it_is_given_and_only_the_operators_it_names() -> None:
    """No eval, exec, compile, import by name, getattr or setattr: no name an agent or a file
    brings becomes code or an attribute; and of Blender's operators, only four."""
    tree = ast.parse(SCRIPT.read_text())
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert not called & {"eval", "exec", "compile", "__import__", "getattr", "setattr", "delattr"}
    operators = {
        (node.value.attr, node.attr)
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and isinstance(node.value.value, ast.Attribute)
        and node.value.value.attr == "ops"
    }
    assert operators <= ALLOWED_OPS
    assert ("render", "render") in operators
