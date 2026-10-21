"""Each feature of an `.ecproj`, read out of its JSON into a value two saves compare by.

A value keeps what the feature means, by name rather than by EffectCraft's numbering, and leaves
out what a save may write out again without changing it, such as a layer's label colour or a
property's interface. The fidelity report opens and saves each corpus file in EffectCraft and
compares its feature's value before and after (lattice RFC-0003, phase 2).
"""

import json
from collections.abc import Callable, Iterator
from typing import Any, Final

Value = list[tuple[object, ...]]
Node = dict[str, Any]

PLACES: Final = 3
"""The decimals a number is compared to: a save writes floats its own way."""


class Project:
    """An `.ecproj`'s items by number, and its compositions' layers."""

    def __init__(self, content: bytes) -> None:
        self.items: dict[str, Node] = json.loads(content)["items"]

    def name(self, item: object) -> str | None:
        return None if item is None else self.items[str(item)]["name"]

    def comps(self) -> Iterator[tuple[str, Node]]:
        for item in self.items.values():
            if item["kind"]["type"] == "Comp":
                yield item["name"], item["kind"]

    def layers(self) -> Iterator[tuple[str, Node]]:
        for name, comp in self.comps():
            for layer in comp["layers"]:
                yield name, layer


def number(value: object) -> object:
    """A value with its numbers rounded, and lists as tuples."""
    if isinstance(value, float):
        return round(value, PLACES)
    if isinstance(value, list):
        return tuple(number(v) for v in value)
    if isinstance(value, dict):
        return tuple(sorted((k, number(v)) for k, v in value.items()))
    return value


def props(node: Node, path: str = "") -> Iterator[tuple[str, Node]]:
    """Each property under a node, by its path of names, as the CLI's `props` lists them."""
    here = f"{path}/{node['match']}" if path else node["match"]
    if node.get("node") == "Prop":
        yield here, node
    for child in node.get("children", []):
        yield from props(child, here)


def compositions(project: Project) -> Value:
    return [
        (name, c["width"], c["height"], c["frame_rate"]["num"], c["duration"])
        for name, c in project.comps()
    ]


def folders(project: Project) -> Value:
    return [
        (item["name"], item["kind"]["type"], project.name(item.get("parent")))
        for item in project.items.values()
    ]


def solids(project: Project) -> Value:
    return [
        (layer["name"], number(project.items[str(layer["source"]["item"])]["kind"]["color"]))
        for _, layer in project.layers()
    ]


def text(project: Project) -> Value:
    """Each text layer's words, font and size."""
    found: Value = []
    for _, layer in project.layers():
        for path, prop in props(layer["props"]):
            if path.endswith("text/sourceText"):
                held = prop["value"]["v"]
                found.append((layer["name"], held["text"], held["font"], number(held["size"])))
    return found


def shapes(project: Project) -> Value:
    """Each shape layer's shapes, by their paths, and their sizes."""
    return [
        (layer["name"], path, number(prop["value"]["v"]))
        for _, layer in project.layers()
        for path, prop in props(layer["props"])
        if "/contents/" in path and path.endswith(("/size", "/points"))
    ]


def keyframes(project: Project) -> Value:
    return [
        (layer["name"], path, [(k["time"], number(k["value"]["v"])) for k in prop["keys"]])
        for _, layer in project.layers()
        for path, prop in props(layer["props"])
        if prop.get("keys")
    ]


def effects(project: Project) -> Value:
    return [
        (layer["name"], [effect["match"] for effect in group.get("children", [])])
        for _, layer in project.layers()
        for group in layer["props"]["children"]
        if group["match"] == "effects"
    ]


def masks(project: Project) -> Value:
    return [
        (layer["name"], path, len(prop["value"]["v"]["vertices"]))
        for _, layer in project.layers()
        for path, prop in props(layer["props"])
        if "/masks/" in path and path.endswith("/path")
    ]


def expressions(project: Project) -> Value:
    return [
        (layer["name"], path, prop["expr"]["text"], prop["expr"]["enabled"])
        for _, layer in project.layers()
        for path, prop in props(layer["props"])
        if prop.get("expr")
    ]


def markers(project: Project) -> Value:
    return [(name, m["time"], m["comment"]) for name, c in project.comps() for m in c["markers"]]


def parenting(project: Project) -> Value:
    names = {layer["id"]: layer["name"] for _, layer in project.layers()}
    return [(layer["name"], names.get(layer["parent"])) for _, layer in project.layers()]


def blend_modes(project: Project) -> Value:
    return [(layer["name"], layer["blend_mode"]) for _, layer in project.layers()]


def precomps(project: Project) -> Value:
    """Each composition's layers, and the item each is of."""
    return [
        (comp, layer["name"], layer["source"]["type"], project.name(layer["source"].get("item")))
        for comp, layer in project.layers()
    ]


READERS: Final[dict[str, Callable[[Project], Value]]] = {
    "compositions": compositions,
    "folders": folders,
    "solids": solids,
    "text": text,
    "shapes": shapes,
    "keyframes": keyframes,
    "effects": effects,
    "masks": masks,
    "expressions": expressions,
    "markers": markers,
    "parenting": parenting,
    "blend_modes": blend_modes,
    "precomps": precomps,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in an `.ecproj`."""
    return READERS[feature](Project(content))
