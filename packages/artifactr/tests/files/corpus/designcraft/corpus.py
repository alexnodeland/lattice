"""DesignCraft's corpus: an `.idml` per feature, each feature's value read out of its XML."""

import io
import zipfile
from collections.abc import Callable

from artifactr.files.app import App
from artifactr.files.designcraft import Subprocess
from tests.files.corpus.designcraft.features import read
from tests.files.corpus.designcraft.make import FEATURES, HERE, TIME
from tests.files.corpus.harness import Corpus


def kept(content: bytes) -> bytes:
    """DesignCraft stamps nothing on an export: two saves in a row are the same bytes."""
    return content


def changed(change: Callable[[str, bytes], bytes | None]) -> bytes:
    """The `text` package with each part as `change` makes it, or left out where it gives None."""
    made = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(FEATURES["text"]())) as source,
        zipfile.ZipFile(made, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for info in source.infolist():
            if (part := change(info.filename, source.read(info))) is not None:
                archive.writestr(zipfile.ZipInfo(info.filename, TIME), part, info.compress_type)
    return made.getvalue()


def bomb() -> bytes:
    """A package whose story inflates to 300 MiB from 300 KiB, written a MiB at a time."""
    made = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(FEATURES["text"]())) as source,
        zipfile.ZipFile(made, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for info in source.infolist():
            if not info.filename.startswith("Stories/"):
                archive.writestr(info, source.read(info))
                continue
            with archive.open(zipfile.ZipInfo(info.filename, TIME), "w", force_zip64=True) as part:
                for _ in range(300):
                    part.write(b" " * (1 << 20))
    return made.getvalue()


def unparsed() -> bytes:
    """A package whose designmap isn't XML."""
    return changed(lambda name, part: b"<Document" if name == "designmap.xml" else part)


def spreadless() -> bytes:
    """A package whose designmap lists a spread it doesn't hold."""
    return changed(lambda name, part: None if name.startswith("Spreads/") else part)


def adapter(cli: str, version: str) -> App:
    return Subprocess(cli, version=version)


CORPUS = Corpus(
    app="designcraft",
    extension=".idml",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={"bomb": bomb, "unparsed": unparsed, "spreadless": spreadless},
)
"""DesignCraft 0.9.0 keeps every feature. A table's content is kept too, but its first save
isn't a fixpoint: the next writes out its alternating strokes, so tables are in no corpus file."""
