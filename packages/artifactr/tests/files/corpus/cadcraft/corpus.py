"""CADCraft's corpus: a `.dxf` per feature, each feature's value read out of its groups."""

import random

from artifactr.files.app import App
from artifactr.files.cadcraft import Subprocess
from tests.files.corpus.cadcraft.features import read
from tests.files.corpus.cadcraft.make import FEATURES, HERE
from tests.files.corpus.harness import Corpus


def kept(content: bytes) -> bytes:
    """CADCraft stamps nothing on a save: two saves in a row are the same bytes."""
    return content


def unread_dwg() -> bytes:
    """A DWG's version, then noise: CADCraft reads its header and refuses it."""
    return b"AC1032" + random.Random(0).randbytes(1 << 16)


def bad_group() -> bytes:
    """A DXF whose first entity's group code isn't a number."""
    return FEATURES["lines"]().replace(b" 10\n0.0", b"abc\n0.0", 1)


def adapter(cli: str, version: str) -> App:
    """CADCraft's CLI confines nothing: its corpus is the only file it is given."""
    return Subprocess(cli, version=version, trusted=True)


CORPUS = Corpus(
    app="cadcraft",
    extension=".dxf",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={"unread_dwg": unread_dwg, "bad_group": bad_group},
)
"""CADCraft 0.8.0 keeps every feature. Its corpus is of DXF, which can be written by hand; its
live tests open and save a DWG of its own making, which it saves as a DWG, the same bytes twice."""
