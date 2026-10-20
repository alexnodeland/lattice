"""PhotoCraft's corpus: a `.psd` per feature, each feature's value read out of its sections."""

import struct

from artifactr.files.app import App
from artifactr.files.photocraft import Subprocess
from tests.files.corpus.harness import Corpus
from tests.files.corpus.photocraft.features import read
from tests.files.corpus.photocraft.make import FEATURES, HERE


def kept(content: bytes) -> bytes:
    """PhotoCraft stamps nothing on a save: two saves in a row are the same bytes."""
    return content


def vast() -> bytes:
    """A `.psd` whose header claims 300,000 pixels square, past the format's 30,000."""
    content = FEATURES["resolution"]()
    return content[:14] + struct.pack(">II", 300_000, 300_000) + content[22:]


def overrun() -> bytes:
    """A `.psd` whose layer section says it is longer than the file."""
    content = FEATURES["pixel_layers"]()
    resources = 30 + struct.unpack(">I", content[26:30])[0]
    return content[:resources] + struct.pack(">I", 1 << 30) + content[resources + 4 :]


def large() -> bytes:
    """A `.psb`, a large document: never opened as a `.psd`, so never saved as one."""
    content = FEATURES["resolution"]()
    return content[:4] + b"\x00\x02" + content[6:]


def adapter(cli: str, version: str) -> App:
    return Subprocess(cli, version=version)


CORPUS = Corpus(
    app="photocraft",
    extension=".psd",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={"vast": vast, "overrun": overrun, "large": large},
)
"""PhotoCraft 0.9.0 keeps every feature."""
