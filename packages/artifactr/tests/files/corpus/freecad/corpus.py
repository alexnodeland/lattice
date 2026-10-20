"""FreeCAD's corpus: an `.FCStd` per feature, made by FreeCAD itself, and its hostile files.

Its makers run `make.py` in the pinned `freecadcmd`, which `ARTIFACTR_TEST_CRAFT_CLI` names, so
its drift is checked live, feature by feature. `python -m tests.files.corpus.freecad.corpus`,
from `packages/artifactr`, with that CLI named, writes the files again.
"""

import base64
import io
import os
import pickle
import subprocess
import tempfile
import zipfile
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Final

from artifactr.files.app import App
from artifactr.files.freecad import Subprocess, fingerprint
from tests.files.corpus.freecad.features import READERS, read
from tests.files.corpus.harness import Corpus

HERE: Final = Path(__file__).parent
MAKE: Final = HERE / "make.py"
TIME: Final = (1980, 1, 1, 0, 0, 0)


def made(feature: str) -> bytes:
    """A feature's file, as `make.py` makes it in FreeCAD now."""
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(
            [
                *(os.environ["ARTIFACTR_TEST_CRAFT_CLI"], "-u", "user.cfg", "-s", "system.cfg"),
                *("--safe-mode", str(MAKE), "--pass", directory, feature),
            ],
            cwd=directory,
            env={"HOME": directory, "LANG": "C.UTF-8", "QT_QPA_PLATFORM": "offscreen"},
            capture_output=True,
            check=True,
            timeout=60,
        )
        return (Path(directory) / f"{feature}.FCStd").read_bytes()


def adapter(cli: str, version: str) -> App:
    """FreeCAD's script confines nothing: its corpus is the only file it is given."""
    return Subprocess(cli, version=version, trusted=True)


# ─── hostile files ────────────────────────────────────────────────────────────


def replaced(feature: str, *changes: tuple[str, str], **parts: bytes) -> bytes:
    """A corpus file with its `Document.xml` changed, each change once, and parts put in place."""
    source = (HERE / f"{feature}.FCStd").read_bytes()
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(source)) as given,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for info in given.infolist():
            if info.filename in parts:
                continue
            data = given.read(info)
            for old, new in changes if info.filename == "Document.xml" else ():
                assert old.encode() in data
                data = data.replace(old.encode(), new.encode(), 1)
            archive.writestr(info, data)
        for name, data in parts.items():
            archive.writestr(zipfile.ZipInfo(name, TIME), data)
    return buffer.getvalue()


def inflating(name: str, head: bytes, size: int, tail: bytes = b"") -> bytes:
    """A document of one part that inflates to `size` bytes of spaces, between a head and a tail."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        entry = zipfile.ZipInfo(name, TIME)
        entry.compress_type = zipfile.ZIP_DEFLATED
        with archive.open(entry, "w", force_zip64=True) as part:
            part.write(head)
            chunk = b" " * (16 << 20)
            for _ in range(size // len(chunk)):
                part.write(chunk)
            part.write(tail)
    return buffer.getvalue()


class _Shell:
    """What a pickled proxy would run, were it ever unpickled."""

    def __reduce__(self) -> tuple[Callable[..., object], tuple[str]]:
        return (os.system, ("touch /tmp/pickled",))


def python(proxy: str) -> bytes:
    """The primitives, with a fifth object, a Python feature whose proxy is `proxy`.

    It is written as FreeCAD saves one, since FreeCAD reads as many objects as each list's count
    says.
    """
    return replaced(
        "primitives",
        ('<Objects Count="4" Dependencies="1">', '<Objects Count="5" Dependencies="1">'),
        ('<ObjectDeps Name="Box"', '<ObjectDeps Name="Py" Count="0"/><ObjectDeps Name="Box"'),
        ("</Objects>", '<Object type="App::FeaturePython" name="Py" id="9"/></Objects>'),
        ('<ObjectData Count="4">', '<ObjectData Count="5">'),
        (
            "</ObjectData>",
            '<Object name="Py"><Properties Count="1" TransientCount="0">'
            f'<Property name="Proxy" type="App::PropertyPythonObject">{proxy}</Property>'
            "</Properties></Object></ObjectData>",
        ),
    )


PICKLED: Final = base64.b64encode(pickle.dumps(_Shell(), protocol=2)).decode()
HOSTILE: Final[dict[str, Callable[[], bytes]]] = {
    # 1 GiB of a shape's part: refused by the zip's directory, nothing inflated.
    "zip_bomb": lambda: inflating("Box.Shape.brp", b"", 1 << 30),
    # A Document.xml of 80 MiB, under the file's limit and past its own.
    "huge_document": lambda: inflating("Document.xml", b"<Document>", 80 << 20, b"</Document>"),
    "deep_nesting": partial(
        replaced, "primitives", ("</Objects>", "<a>" * 100_000 + "</a>" * 100_000 + "</Objects>")
    ),
    "entity": partial(
        replaced,
        "primitives",
        ("<Document ", '<!DOCTYPE d [<!ENTITY e SYSTEM "file:///etc/passwd">]><Document '),
    ),
    "pickled_proxy": partial(python, f'<Python value="{PICKLED}" encoded="yes"/>'),
    "freecad_module_proxy": partial(
        python, '<Python value="e30=" encoded="yes" module="Draft" class="Wire"/>'
    ),
    "gui_proxy": partial(
        replaced,
        "gui",
        **{
            "GuiDocument.xml": b'<Document><ViewProvider name="Box"><Property name="Proxy" '
            b'type="App::PropertyPythonObject"><Python value="e30=" module="Draft"/>'
            b"</Property></ViewProvider></Document>"
        },
    ),
    "external_link": partial(
        replaced,
        "primitives",
        (
            "</Objects>",
            '<Object type="App::Link" name="L" id="9"/><XLink file="/etc/passwd" name="B"/>'
            "</Objects>",
        ),
    ),
    # Cut's base is the fusion, whose base is Cut: FreeCAD opens it, and the script refuses it.
    "cycle": partial(replaced, "booleans", ('<Link value="Box"/>', '<Link value="Fusion"/>')),
}

CORPUS = Corpus(
    app="freecad",
    extension=".FCStd",
    folder=HERE,
    makers={feature: partial(made, feature) for feature in READERS},
    read=read,
    kept=fingerprint,
    adapter=adapter,
    made_by_app=True,
    hostile=HOSTILE,
)
"""FreeCAD 1.1.4 keeps every feature, a save leaving out only its time; the GUI's part is put
back by the adapter, since its console drops it."""


if __name__ == "__main__":
    for feature in READERS:
        (HERE / f"{feature}.FCStd").write_bytes(made(feature))
