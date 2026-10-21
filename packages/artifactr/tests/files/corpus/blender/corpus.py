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


def pointed(struct_name: str, field: bytes, target: str) -> Callable[[bytearray], None]:
    """A change pointing a field of a struct's first record at the first block of another."""

    def change(data: bytearray) -> None:
        catalogue = read(bytes(data)).catalogue
        offset, _ = catalogue.field(catalogue.index(struct_name), field)
        _, at = first(data, struct_name)
        head, _ = first(data, target)
        address = HEAD.unpack_from(data, head)[2]
        struct.pack_into("<Q", data, at + offset, address)

    return change


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
    "confused_pointer": partial(changed, "camera_light", pointed("Object", b"adt", "Camera")),
    # The cube, its own parent: the scan allows a parent, and the script refuses the cycle.
    "cycle": partial(changed, "transforms", pointed("Object", b"parent", "Object")),
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
