"""DeckCraft's corpus: a `.pptx` per feature, each feature's value read out of its OOXML."""

from artifactr.files.app import App
from artifactr.files.deckcraft import Subprocess
from tests.files.corpus import package
from tests.files.corpus.deckcraft.features import read
from tests.files.corpus.deckcraft.make import FEATURES, HERE
from tests.files.corpus.harness import Corpus


def adapter(cli: str, version: str) -> App:
    # The corpus is lattice's own files, made here: trusted, as DeckCraft's CLI confines nothing.
    return Subprocess(cli, version=version, trusted=True)


CORPUS = Corpus(
    app="deckcraft",
    extension=".pptx",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=package.canonical,
    adapter=adapter,
    hostile={
        "bomb": lambda: package.bomb(FEATURES["text"](), "ppt/slides/slide1.xml"),
        "untyped": lambda: package.untyped(FEATURES["text"]()),
    },
)
"""DeckCraft 0.7.0 keeps every feature. Its second save writes the XML of the first in another
way, `<a:p/>` as `<a:p></a:p>`, so saving twice is held to the parts' canonical form."""
