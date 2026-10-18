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


def bomb() -> bytes:
    """A `.docx` whose document inflates to 300 MiB from 300 KiB, written a MiB at a time."""
    made = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(FEATURES["text"]())) as source,
        zipfile.ZipFile(made, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for name in source.namelist():
            part = source.read(name)
            if name != "word/document.xml":
                archive.writestr(name, part)
                continue
            head, _, tail = part.partition(b"<w:body>")
            with archive.open(name, "w", force_zip64=True) as stream:
                stream.write(head + b"<w:body><!--")
                for _ in range(300):
                    stream.write(b" " * (1 << 20))
                stream.write(b"-->" + tail)
    return made.getvalue()


def untyped() -> bytes:
    """A `.docx` whose content types aren't XML."""
    made = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(FEATURES["text"]())) as source,
        zipfile.ZipFile(made, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for name in source.namelist():
            part = b"<Types" if name == "[Content_Types].xml" else source.read(name)
            archive.writestr(name, part)
    return made.getvalue()


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
    hostile={"bomb": bomb, "untyped": untyped},
)
"""WordCraft 0.7.0 keeps every feature."""
