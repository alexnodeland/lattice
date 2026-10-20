"""VectorCraft's corpus: an `.svg` per feature, each feature's value read out of its elements."""

from artifactr.files.app import App
from artifactr.files.vectorcraft import Subprocess
from tests.files.corpus.harness import Corpus
from tests.files.corpus.vectorcraft.features import read
from tests.files.corpus.vectorcraft.make import FEATURES, HERE, svg


def kept(content: bytes) -> bytes:
    """VectorCraft stamps nothing on a save: two saves in a row are the same bytes."""
    return content


def laughs() -> bytes:
    """An SVG whose doctype declares entities that expand to a billion words."""
    declared = "".join(f'<!ENTITY e{i} "{f"&e{i - 1};" * 10}">' for i in range(1, 10))
    return (
        f'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY e0 "lol">{declared}]>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text>&e9;</text></svg>'
    ).encode()


def external() -> bytes:
    """An SVG whose words are a file of this machine's, by an external entity."""
    return (
        b'<?xml version="1.0"?><!DOCTYPE svg [<!ENTITY x SYSTEM "file:///etc/passwd">]>'
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><text>&x;</text></svg>'
    )


def nested() -> bytes:
    """An SVG of groups nested a hundred thousand deep."""
    return svg("<g>" * 100_000 + "</g>" * 100_000)


def unclosed() -> bytes:
    """An SVG whose root element is never closed."""
    return svg('<rect width="5" height="5"/>').removesuffix(b"</svg>\n")


def adapter(cli: str, version: str) -> App:
    return Subprocess(cli, version=version)


CORPUS = Corpus(
    app="vectorcraft",
    extension=".svg",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={"laughs": laughs, "external": external, "nested": nested, "unclosed": unclosed},
)
"""VectorCraft 0.12.0 keeps every feature. A save sets an SVG's title to the file's name, which
two saves then agree on, so no corpus file holds a title: its loss is in the adapter's documents.
It writes every shape as a path and bakes transforms into the geometry, which the features'
values leave out."""
