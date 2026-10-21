"""A layout's format, told from its package's `mimetype`."""

import io
import zipfile

import pytest

from artifactr.files.designcraft import media_type
from artifactr.files.manifest import IDML

TIME = (1980, 1, 1, 0, 0, 0)
"""Every entry's time, so a package, and a test's id from it, is the same in every process."""


def package(**parts: bytes) -> bytes:
    made = io.BytesIO()
    with zipfile.ZipFile(made, "w") as archive:
        for name, part in parts.items():
            archive.writestr(zipfile.ZipInfo(name, TIME), part)
    return made.getvalue()


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (package(mimetype=IDML.encode()), IDML),
        (package(mimetype=f"{IDML}\n".encode()), IDML),
        (package(mimetype=b"application/vnd.oasis.opendocument.text"), None),
        (package(designmap=b"<Document/>"), None),
        (b'{"format": "designcraft"}', None),
        (b"", None),
    ],
)
def test_a_layouts_format_is_its_packages_mimetype(content: bytes, expected: str) -> None:
    assert media_type(content) == expected


def test_a_mimetype_is_read_no_further_than_its_start() -> None:
    assert media_type(package(mimetype=IDML.encode() + b" " * (1 << 20))) == IDML
