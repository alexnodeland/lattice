"""A Photoshop document's format, told from its header."""

import pytest

from artifactr.files.manifest import PSD
from artifactr.files.photocraft import media_type


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"8BPS\x00\x01\x00\x00", PSD),
        (b"8BPS\x00\x02\x00\x00", None),
        (b"8BPS\x00\x03", None),
        (b"\x89PNG\r\n\x1a\n", None),
        (b"", None),
    ],
)
def test_a_documents_format_is_read_from_its_header(content: bytes, expected: str) -> None:
    assert media_type(content) == expected
