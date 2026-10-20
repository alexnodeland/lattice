"""Whether bytes are a `.figcraft`, told from its document."""

import io
import zipfile

import pytest

from artifactr.files.figcraft import media_type
from artifactr.files.manifest import FIGCRAFT


def zipped(name: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (zipped("document.json", b'{"format":"figcraft","version":1}'), FIGCRAFT),
        (zipped("document.json", b' { "format" : "figcraft" , "nodes": {}}'), FIGCRAFT),
        (zipped("document.json", b'{"format":"fig"}'), None),
        (zipped("document.json", b'{"version":1,"format":"figcraft"}'), None),
        (zipped("canvas.fig", b"fig-kiwi"), None),
        (zipped("document.json", b'{"format":"figcraft"}')[:40], None),
        (b'{"format":"figcraft"}', None),
        (b"", None),
    ],
)
def test_a_figcraft_is_told_by_its_documents_format(content: bytes, expected: str) -> None:
    assert media_type(content) == expected
