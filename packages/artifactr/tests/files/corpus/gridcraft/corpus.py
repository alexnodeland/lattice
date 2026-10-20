"""GridCraft's corpus: a `.xlsx` per feature, each feature's value read out of its OOXML."""

from artifactr.files.app import App
from artifactr.files.gridcraft import Subprocess
from tests.files.corpus import package
from tests.files.corpus.gridcraft.features import read
from tests.files.corpus.gridcraft.make import FEATURES, HERE
from tests.files.corpus.harness import Corpus


def adapter(cli: str, version: str) -> App:
    # The corpus is lattice's own files, made here: trusted, as GridCraft's CLI confines nothing.
    return Subprocess(cli, version=version, trusted=True)


CORPUS = Corpus(
    app="gridcraft",
    extension=".xlsx",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=package.parts,
    adapter=adapter,
    hostile={
        "bomb": lambda: package.bomb(FEATURES["values"](), "xl/worksheets/sheet1.xml"),
        "untyped": lambda: package.untyped(FEATURES["values"]()),
    },
)
"""GridCraft 0.8.0 keeps every feature."""
