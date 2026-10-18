"""WordCraft's corpus: a `.docx` per feature, each feature's value read out of its OOXML."""

import zipfile
from io import BytesIO

from artifactr.files.app import App
from artifactr.files.wordcraft import STAMPED, Subprocess
from tests.files.corpus.harness import Corpus
from tests.files.corpus.wordcraft.features import read
from tests.files.corpus.wordcraft.make import FEATURES, HERE


def parts(content: bytes) -> dict[str, bytes]:
    """A `.docx`'s parts, without the one each save stamps."""
    with zipfile.ZipFile(BytesIO(content)) as archive:
        return {name: archive.read(name) for name in archive.namelist() if name not in STAMPED}


def adapter(cli: str, version: str) -> App:
    return Subprocess(cli, version=version)


CORPUS = Corpus(
    app="wordcraft",
    extension=".docx",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=parts,
    adapter=adapter,
)
"""WordCraft 0.7.0 keeps every feature."""
