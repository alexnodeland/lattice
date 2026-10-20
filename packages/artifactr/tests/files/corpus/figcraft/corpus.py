"""FigCraft's corpus: a `.figcraft` per feature, each feature's value read out of its document."""

import io
import json
import zipfile
from typing import Any

from artifactr.files.app import App
from artifactr.files.figcraft import Subprocess
from tests.files.corpus.figcraft.features import read
from tests.files.corpus.figcraft.make import FEATURES, HERE, TIME
from tests.files.corpus.harness import Corpus


def kept(content: bytes) -> bytes:
    """FigCraft stamps nothing on a save: two saves in a row are the same bytes."""
    return content


def document() -> dict[str, Any]:
    """The groups feature's document, to break."""
    with zipfile.ZipFile(io.BytesIO(FEATURES["groups"]())) as archive:
        return json.loads(archive.read("document.json"))


def zipped(content: bytes) -> bytes:
    """A `.figcraft` holding a document of these bytes."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(zipfile.ZipInfo("document.json", TIME), content, zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def not_json() -> bytes:
    """A document that says it is a `.figcraft`, and then isn't JSON."""
    return zipped(b'{"format": "figcraft", nope')


def future_version() -> bytes:
    """A document of a format version FigCraft doesn't know."""
    return zipped(json.dumps({**document(), "version": 99}).encode())


def unknown_layer() -> bytes:
    """A document with a layer of a type FigCraft doesn't know."""
    held = document()
    held["nodes"]["3"]["type"] = "hologram"
    return zipped(json.dumps(held).encode())


def adapter(cli: str, version: str) -> App:
    """FigCraft's CLI confines nothing: its corpus is the only file it is given."""
    return Subprocess(cli, version=version, trusted=True)


CORPUS = Corpus(
    app="figcraft",
    extension=".figcraft",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={
        "not_json": not_json,
        "future_version": future_version,
        "unknown_layer": unknown_layer,
    },
)
"""FigCraft 0.6.0 keeps every feature. A layer cycle, a dangling child, an unknown page and a
document that inflates to 300 MiB of spaces are each opened, not refused, so none is a hostile
file here."""
