"""Whether bytes are an SVG, told by their root element."""

import gzip

import pytest

from artifactr.files.manifest import SVG
from artifactr.files.vectorcraft import media_type

ROOT = b'<svg xmlns="http://www.w3.org/2000/svg"/>'


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (ROOT, SVG),
        (b'\xef\xbb\xbf<?xml version="1.0"?>\n<!-- drawn by hand -->\n' + ROOT, SVG),
        (b'<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "svg11.dtd">' + ROOT, SVG),
        (b'<!DOCTYPE svg [<!ENTITY a "b">]>' + ROOT, SVG),
        (b'<svg:svg xmlns:svg="http://www.w3.org/2000/svg"/>', SVG),
        (b'<html><svg xmlns="http://www.w3.org/2000/svg"/></html>', None),
        (b"<svgx/>", None),
        (gzip.compress(ROOT), None),
        (b"%PDF-1.7", None),
        (b"", None),
    ],
)
def test_an_svg_is_told_by_its_root_element(content: bytes, expected: str | None) -> None:
    assert media_type(content) == expected
