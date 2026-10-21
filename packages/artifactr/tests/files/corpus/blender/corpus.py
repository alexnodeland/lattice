"""Blender's corpus: a `.blend` per feature, made by Blender itself, and its hostile files.

Its makers run `make.py` in the pinned `blender`, which `ARTIFACTR_TEST_CRAFT_CLI` names, so its
drift is checked live, feature by feature. `python -m tests.files.corpus.blender.corpus`, from
`packages/artifactr`, with that CLI named, writes the files again, and the hostile files only
Blender can make, in `hostile/`.
"""

import io
import os
import struct
import subprocess
import tempfile
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Final

import zstandard

from artifactr.files.app import App
from artifactr.files.blender import Subprocess, fingerprint
from artifactr.files.blender.document import HEAD, HEADER, read
from artifactr.files.blender.headless import ARGUMENTS
from tests.files.corpus.blender.features import READERS
from tests.files.corpus.blender.features import read as value
from tests.files.corpus.harness import Corpus

HERE: Final = Path(__file__).parent
HOSTILE_FOLDER: Final = HERE / "hostile"
MAKE: Final = HERE / "make.py"


def made(feature: str) -> bytes:
    """A feature's file, as `make.py` makes it in Blender now."""
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(
            [
                *(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], *ARGUMENTS),
                *(str(MAKE), "--", "--pass", directory, feature),
            ],
            cwd=directory,
            env={"HOME": directory, "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            capture_output=True,
            check=True,
            timeout=120,
        )
        return (Path(directory) / f"{feature}.blend").read_bytes()


def adapter(cli: str, version: str) -> App:
    """Blender's script confines nothing: its corpus is the only file it is given."""
    return Subprocess(cli, version=version, trusted=True)


# ─── hostile files ────────────────────────────────────────────────────────────


def plain(feature: str) -> bytearray:
    """A corpus file's bytes, uncompressed, to change."""
    return bytearray(read((HERE / f"{feature}.blend").read_bytes()).data)


def changed(feature: str, change: Callable[[bytearray], None]) -> bytes:
    """A corpus file, uncompressed, changed."""
    data = plain(feature)
    change(data)
    return bytes(data)


def first(data: bytearray, struct_name: str) -> tuple[int, int]:
    """Where the first block of a struct starts its head, and where its bytes start."""
    blend = read(bytes(data))
    block = next(
        b for b in blend.blocks if b.index and blend.catalogue.name(b.index) == struct_name
    )
    return block.start, block.bytes_start


def offset_of(data: bytearray, struct_name: str, path: str) -> int:
    """Where a field is in a struct's record, by its path through the structs it holds."""
    catalogue = read(bytes(data)).catalogue
    offset, name = 0, struct_name
    for part in path.split("."):
        at, kind = next(
            (o, catalogue.types[k].decode())
            for o, k, f, _ in catalogue.fields(catalogue.index(name))
            if f.lstrip(b"*").split(b"[")[0] == part.encode()
        )
        offset, name = offset + at, kind
    return offset


def address_of(data: bytearray, struct_name: str) -> int:
    """The address of the first block of a struct."""
    head, _ = first(data, struct_name)
    return HEAD.unpack_from(data, head)[2]


def pointed(struct_name: str, path: str, target: str) -> Callable[[bytearray], None]:
    """A change pointing a field of a struct's first record at the first block of another."""

    def change(data: bytearray) -> None:
        _, at = first(data, struct_name)
        address = address_of(data, target)
        struct.pack_into("<Q", data, at + offset_of(data, struct_name, path), address)

    return change


def written(struct_name: str, path: str, value: bytes) -> Callable[[bytearray], None]:
    """A change writing bytes into a field of a struct's first record."""

    def change(data: bytearray) -> None:
        at = first(data, struct_name)[1] + offset_of(data, struct_name, path)
        data[at : at + len(value)] = value

    return change


def inserted(
    struct_name: str | None, payload: bytes, address: int = 0x10
) -> Callable[[bytearray], None]:
    """A change putting a data block of a struct, or raw, right after the first object."""

    def change(data: bytearray) -> None:
        catalogue = read(bytes(data)).catalogue
        index = 0 if struct_name is None else catalogue.index(struct_name)
        count = 1 if struct_name is None else len(payload) // catalogue.size(index)
        _, at = first(data, "Object")
        end = next(b.end for b in read(bytes(data)).blocks if b.bytes_start == at)
        data[end:end] = HEAD.pack(b"DATA", index, address, len(payload), count) + payload

    return change


def twice(data: bytearray) -> None:
    """The first data block after the first object written twice, at one address."""
    blocks = read(bytes(data)).blocks
    _, at = first(data, "Object")
    owner = next(i for i, b in enumerate(blocks) if b.bytes_start == at)
    block = next(b for b in blocks[owner:] if b.code == b"DATA")
    data[block.end : block.end] = data[block.start : block.end]


def readdressed(struct_name: str, target: str) -> Callable[[bytearray], None]:
    """A change moving the first block of a struct to the address of another's first block."""

    def change(data: bytearray) -> None:
        head, _ = first(data, struct_name)
        values = list(HEAD.unpack_from(data, head))
        values[2] = address_of(data, target)
        HEAD.pack_into(data, head, *values)

    return change


def restructed(struct_name: str) -> Callable[[bytearray], None]:
    """A change making the first object's block say it holds another struct, of the same size."""

    def change(data: bytearray) -> None:
        head, _ = first(data, "Object")
        values = list(HEAD.unpack_from(data, head))
        values[1] = read(bytes(data)).catalogue.index(struct_name)
        HEAD.pack_into(data, head, *values)

    return change


def size_of(struct_name: str) -> int:
    catalogue = read(corpus_file("primitives")).catalogue
    return catalogue.size(catalogue.index(struct_name))


def material_array(data: bytearray) -> None:
    """A mesh's array of materials holding a pointer at an object."""
    blend = read(bytes(data))
    _, at = first(data, "Mesh")
    (array,) = struct.unpack_from("<Q", data, at + offset_of(data, "Mesh", "mat"))
    owner = next(i for i, b in enumerate(blend.blocks) if b.bytes_start == at)
    raw = next(b for b in blend.blocks[owner:] if b.address == array)
    struct.pack_into("<Q", data, raw.bytes_start, address_of(data, "Object"))


def headed(field: int, value: int) -> Callable[[bytearray], None]:
    """A change setting a field of the first object's head: 1 its struct, 3 its length, 4 its
    count."""

    def change(data: bytearray) -> None:
        start, _ = first(data, "Object")
        values = list(HEAD.unpack_from(data, start))
        values[field] = value
        HEAD.pack_into(data, start, *values)

    return change


def bomb() -> bytes:
    """A zstd frame that inflates to 2 GiB of zeros, past any limit, from a few kilobytes."""
    compressor = zstandard.ZstdCompressor(level=19)
    stream = io.BytesIO()
    with compressor.stream_writer(stream, closefd=False) as writer:
        writer.write(HEADER)
        chunk = bytes(64 << 20)
        for _ in range(32):
            writer.write(chunk)
    return stream.getvalue()


def corpus_file(feature: str) -> bytes:
    """A corpus file, as committed."""
    return (HERE / f"{feature}.blend").read_bytes()


def blender_made(name: str) -> bytes:
    """A hostile file only Blender can make, as `make.py` made it."""
    return (HOSTILE_FOLDER / f"{name}.blend").read_bytes()


HOSTILE: Final[dict[str, Callable[[], bytes]]] = {
    # Each made by Blender 5.2.2: a text it would run if scripts ran, a driver whose Python runs
    # unless its bytecode fails Blender's test, a driver Blender's own evaluator runs regardless,
    # an object linked from another file, a packed and an external image, a script node naming a
    # file, and an animation.
    **{
        path.stem: partial(blender_made, path.stem)
        for path in sorted(HOSTILE_FOLDER.glob("*.blend"))
    },
    # 2 GiB of zeros behind a header, in a few kilobytes of zstd.
    "zstd_bomb": bomb,
    "gzip": lambda: b"\x1f\x8b\x08" + bytes(64),
    # Blender before 5.0's header, its pointers 4 bytes: a reader that trusted it would misread
    # every head.
    "pointer_size": partial(
        changed, "primitives", lambda d: d.__setitem__(slice(0, 12), b"BLENDER_v405")
    ),
    "big_endian": partial(
        changed, "primitives", lambda d: d.__setitem__(slice(0, 12), b"BLENDER-V405")
    ),
    "another_version": partial(
        changed, "primitives", lambda d: d.__setitem__(slice(13, 17), b"0503")
    ),
    # A head that says its block is longer than the file, or of a negative length.
    "lying_length": partial(changed, "primitives", headed(3, 1 << 40)),
    "negative_length": partial(changed, "primitives", headed(3, -1)),
    # A head whose count says a million records of its struct, in the bytes of one.
    "huge_count": partial(changed, "primitives", headed(4, 1_000_000)),
    "no_struct": partial(changed, "primitives", headed(1, 30_000)),
    "after_the_end": lambda: bytes(plain("primitives")) + b"#!/bin/sh\nid\n",
    # The catalogue of structs, one byte changed: Blender would read structs by it.
    "another_catalogue": partial(
        changed, "primitives", lambda d: d.__setitem__(d.index(b"SDNANAME") + 20, 0x41)
    ),
    # An object's animation, pointed at a camera's block: Blender checks a pointed block's size
    # alone, so any block large enough would be read as animation.
    "confused_pointer": partial(changed, "camera_light", pointed("Object", "adt", "Camera")),
    # A light's parent pointed at a camera's block, a light's data at a mesh's, and a material's
    # node's data-block, which Blender reads by the node's kind, at an object.
    "confused_parent": partial(changed, "camera_light", pointed("Object", "parent", "Camera")),
    "confused_data": partial(changed, "camera_light", pointed("Object", "data", "Mesh")),
    "node_data_block": partial(changed, "materials", pointed("bNode", "id", "Object")),
    # An address twice in one data-block's data, and two data-blocks at one address: Blender keeps
    # the last of each.
    "same_address": partial(changed, "primitives", twice),
    "same_data_block_address": partial(changed, "camera_light", readdressed("Camera", "Lamp")),
    # An object's block saying it holds a camera, and an object holding an object as its data.
    "code_and_struct": partial(changed, "camera_light", restructed("Camera")),
    "embedded_object": lambda: changed("primitives", inserted("Object", bytes(size_of("Object")))),
    # A list and a `void *` Blender reads by their context: a Freestyle module's list, which runs
    # a script, and a node's storage, each pointed at an object.
    "freestyle_module": partial(
        changed, "primitives", pointed("ViewLayer", "freestyle_config.modules.first", "Object")
    ),
    "node_storage": partial(changed, "materials", pointed("bNode", "storage", "Object")),
    # A mesh's materials, an array of pointers, holding a pointer at an object.
    "material_array": partial(changed, "materials", material_array),
    # Older versions in FileGlobal, so Blender's code for older files would run; a node of another
    # name; and an allowed node with another node's number.
    "older_file": partial(changed, "primitives", written("FileGlobal", "minversion", b"\x01\x01")),
    "image_node": partial(
        changed, "materials", written("bNode", "idname", b"ShaderNodeTexImage\0")
    ),
    "node_number": partial(changed, "materials", written("bNode", "type", b"\x22\x00")),
    # Half a million node sockets, every pointer of each set: more work than a scan may take.
    "dense_records": lambda: changed(
        "materials", inserted("bNodeSocket", b"\x11" * size_of("bNodeSocket") * 500_000)
    ),
    # The cube, its own parent: the scan allows a parent, and the script refuses the cycle.
    "cycle": partial(changed, "transforms", pointed("Object", "parent", "Object")),
}

CORPUS = Corpus(
    app="blender",
    extension=".blend",
    folder=HERE,
    makers={feature: partial(made, feature) for feature in READERS},
    read=value,
    kept=fingerprint,
    adapter=adapter,
    made_by_app=True,
    hostile=HOSTILE,
)
"""Blender 5.2.2 keeps every feature, a save leaving out only its path and a counter."""


if __name__ == "__main__":
    for feature in READERS:
        (HERE / f"{feature}.blend").write_bytes(made(feature))
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(
            [
                *(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], *ARGUMENTS),
                *(str(MAKE), "--", "--pass", str(HERE), "hostile"),
            ],
            cwd=directory,
            env={"HOME": directory, "LANG": "C.UTF-8", "PATH": "/usr/bin:/bin"},
            check=True,
            timeout=600,
        )
