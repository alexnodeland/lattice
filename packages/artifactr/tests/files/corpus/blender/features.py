"""Each feature of a `.blend`, read out of its blocks into a value two saves compare by.

A value keeps what the feature means: each object's name, place, rotation and scale, a mesh's
size, a material's colour, each modifier's settings, a camera's lens, a light's type and power,
the collections and what they hold, and the scene's render size and engine. It leaves out what
Blender stamps or derives: addresses, session ids, the thumbnail (lattice RFC-0003, phase 2).

It reads the blocks by the catalogue the scan checks, `DNA1`, field by field, as Blender lays
each struct out.
"""

import math
import struct
from collections.abc import Callable
from typing import Any, Final

from artifactr.files.blender import document

Value = list[tuple[object, ...]]

PLACES: Final = 5
"""The decimals a number is compared to."""

FORMATS: Final = {"float": "f", "int": "i", "short": "h", "char": "b", "uchar": "B"}


class Scene:
    """A file's blocks, by struct, each record a reader of its fields by name."""

    def __init__(self, content: bytes) -> None:
        blend = document.read(content)
        self.catalogue = blend.catalogue
        self.data = blend.data
        self.records: dict[str, list[int]] = {}
        """Where each record of each struct starts, by the struct's name, in file order."""
        self.at = {block.address: block.bytes_start for block in blend.blocks}
        """Where the bytes of the block at an address start."""
        for block in blend.blocks:
            if block.index == document.RAW or block.code in {b"DNA1", b"ENDB"}:
                continue
            size = self.catalogue.size(block.index)
            self.records.setdefault(self.catalogue.name(block.index), []).extend(
                block.bytes_start + each * size for each in range(block.count)
            )

    def read(self, struct_name: str, start: int, path: str) -> Any:
        """A field's value, by a dotted path through the structs it holds: a number, a list of
        numbers, a string or an address."""
        index = self.catalogue.index(struct_name)
        head, _, rest = path.partition(".")
        offset, size, kind, name = next(
            (o, s, self.catalogue.types[k].decode(), f)
            for o, k, f, s in self.catalogue.fields(index)
            if f.lstrip(b"*").split(b"[")[0] == head.encode()
        )
        if rest:
            return self.read(kind, start + offset, rest)
        if name.startswith(b"*"):
            return struct.unpack_from("<Q", self.data, start + offset)[0]
        if kind == "char" and b"[" in name:
            return self.data[start + offset : start + offset + size].split(b"\0")[0].decode()
        code = FORMATS[kind]
        values = struct.unpack_from(
            f"<{size // struct.calcsize(code)}{code}", self.data, start + offset
        )
        rounded = [round(v, PLACES) if isinstance(v, float) else v for v in values]
        return rounded[0] if len(rounded) == 1 else tuple(rounded)

    def each(self, struct_name: str, *paths: str) -> list[tuple[Any, ...]]:
        """Every record of a struct, as the values of the paths given."""
        return [
            tuple(self.read(struct_name, start, path) for path in paths)
            for start in self.records.get(struct_name, [])
        ]

    def name(self, address: int) -> str:
        """The name of the data-block at an address, without its code."""
        return str(self.read("ID", self.at[address], "name"))[2:]


def objects(scene: Scene) -> Value:
    """Each object's name, place, rotation in degrees and scale."""
    return [
        (name[2:], loc, tuple(round(math.degrees(r), 3) for r in rot), scale)
        for name, loc, rot, scale in scene.each("Object", "id.name", "loc", "rot", "size")
    ]


def primitives(scene: Scene) -> Value:
    """The objects, and each mesh's vertices and faces."""
    meshes = [
        (name[2:], verts, faces)
        for name, verts, faces in scene.each("Mesh", "id.name", "totvert", "totpoly")
    ]
    return [*objects(scene), *meshes]


def materials(scene: Scene) -> Value:
    """Each material's colour, metallic and roughness."""
    return [
        (name[2:], colour, metallic, roughness)
        for name, *colour, metallic, roughness in scene.each(
            "Material", "id.name", "r", "g", "b", "metallic", "roughness"
        )
    ]


MODIFIERS: Final = {
    "SubsurfModifierData": ("levels",),
    "BevelModifierData": ("value", "res"),
    "ArrayModifierData": ("count",),
    "MirrorModifierData": ("flag",),
    "SolidifyModifierData": ("offset",),
}


def modifiers(scene: Scene) -> Value:
    """Each modifier's name and type, and the settings its command sets."""
    return [
        (kind, *row)
        for kind, fields in MODIFIERS.items()
        for row in scene.each(kind, "modifier.name", "modifier.type", *fields)
    ]


def camera_light(scene: Scene) -> Value:
    """The objects, each camera's lens, and each light's type, colour and power."""
    cameras = [(name[2:], lens) for name, lens in scene.each("Camera", "id.name", "lens")]
    lights = [
        (name[2:], kind, colour, energy)
        for name, kind, *colour, energy in scene.each(
            "Lamp", "id.name", "type", "r", "g", "b", "energy_new"
        )
    ]
    return [*objects(scene), *cameras, *lights]


def collections(scene: Scene) -> Value:
    """Each collection's name, the collections in it and the objects in it."""
    found: Value = []
    for start in scene.records.get("Collection", []):
        name = str(scene.read("Collection", start, "id.name"))[2:]
        children = _listed(
            scene,
            scene.read("Collection", start, "children.first"),
            "CollectionChild",
            "collection",
        )
        held = _listed(
            scene, scene.read("Collection", start, "gobject.first"), "CollectionObject", "ob"
        )
        found.append((name, tuple(children), tuple(held)))
    return found


def _listed(scene: Scene, first: int, struct_name: str, field: str) -> list[str]:
    """The names a linked list's links point at, from its first."""
    names: list[str] = []
    at = first
    while at:
        start = scene.at[at]
        names.append(scene.name(scene.read(struct_name, start, field)))
        at = scene.read(struct_name, start, "next")
    return names


def render_settings(scene: Scene) -> Value:
    """The scene's render size and engine."""
    return [
        (name[2:], *rest)
        for name, *rest in scene.each("Scene", "id.name", "r.xsch", "r.ysch", "r.engine")
    ]


READERS: Final[dict[str, Callable[[Scene], Value]]] = {
    "primitives": primitives,
    "transforms": objects,
    "materials": materials,
    "modifiers": modifiers,
    "camera_light": camera_light,
    "collections": collections,
    "render_settings": render_settings,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a file."""
    return READERS[feature](Scene(content))
