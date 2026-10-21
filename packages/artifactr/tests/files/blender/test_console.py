"""The pure part of the script Blender runs: its arguments' checks, and what it refuses itself.

The script imports Blender's modules, which no pull request has, so it is imported here with
stand-ins for them, under a name that doesn't run it; `test_live.py` runs it in Blender itself.
"""

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
    for kind in ("meshes", "materials", "cameras", "lights", "scenes", "collections"):
        setattr(data, kind, [])
    data.texts, data.libraries, data.images = [], [], []
    objects = {n: SimpleNamespace(name=n, parent=None, animation_data=None) for n in "abc"}
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
    with pytest.raises(console.Refused, match="a text"):
        console.inert()
