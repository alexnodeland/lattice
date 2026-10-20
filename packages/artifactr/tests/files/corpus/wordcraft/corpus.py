"""WordCraft's corpus: a `.docx` per feature, each feature's value read out of its OOXML."""

from functools import partial

from artifactr.files.app import App
from artifactr.files.wordcraft import STAMPED, Subprocess
from tests.files.corpus import package
from tests.files.corpus.harness import Corpus
from tests.files.corpus.wordcraft.features import read
from tests.files.corpus.wordcraft.make import FEATURES, HERE


def adapter(cli: str, version: str) -> App:
    return Subprocess(cli, version=version)


CORPUS = Corpus(
    app="wordcraft",
    extension=".docx",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=partial(package.parts, stamped=STAMPED),
    adapter=adapter,
    hostile={
        "bomb": lambda: package.bomb(FEATURES["text"](), "word/document.xml"),
        "untyped": lambda: package.untyped(FEATURES["text"]()),
    },
)
"""WordCraft 0.7.0 keeps every feature."""
