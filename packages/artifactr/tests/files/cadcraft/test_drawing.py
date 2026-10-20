"""A drawing's format, told from its first bytes."""

import pytest

from artifactr.files.cadcraft import media_type
from artifactr.files.manifest import DWG, DXF


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (b"AC1032\x00\x00", DWG),
        (b"AC1015", DWG),
        (b"  0\nSECTION\n  2\nHEADER\n", DXF),
        (b"\xef\xbb\xbf0\r\nSECTION\r\n", DXF),
        (b"999\nmade by hand\n  0\nSECTION\n", DXF),
        (b"AutoCAD Binary DXF\r\n\x1a\x00\x00", DXF),
        (b"  0\nEOF\n", None),
        (b"AC10", None),
        (b"%PDF-1.7", None),
        (b"", None),
    ],
)
def test_a_drawings_format_is_read_from_its_first_bytes(content: bytes, expected: str) -> None:
    assert media_type(content) == expected
