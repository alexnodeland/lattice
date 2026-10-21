"""FreeCAD documents written by hand, as small as the scan reads them, for the adapter's tests."""

import io
import zipfile
from typing import Final

TIME: Final = (1980, 1, 1, 0, 0, 0)


def xml(objects: str = "", *, label: str = "Model", modified: str = "2026-10-20T00:00:00Z") -> str:
    """A `Document.xml`: its label, the time it was saved, and its objects' elements."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Document SchemaVersion="4" ProgramVersion="1.1R20260928" FileVersion="1">\n'
        '<Properties Count="2">\n'
        f'<Property name="Label" type="App::PropertyString"><String value="{label}"/></Property>\n'
        '<Property name="LastModifiedDate" type="App::PropertyString">\n'
        f'    <String value="{modified}"/>\n'
        "</Property>\n"
        "</Properties>\n"
        f"<Objects>{objects}</Objects>\n"
        "</Document>\n"
    )


def obj(name: str, kind: str) -> str:
    """An object's element in `Objects`."""
    return f'<Object type="{kind}" name="{name}" id="1"/>'


def fcstd(document: str | bytes | None = None, **parts: str | bytes) -> bytes:
    """A zip of `Document.xml`, a box's by default, and the other parts given, in order."""
    named = {"Document.xml": xml(obj("Box", "Part::Box")) if document is None else document}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in {**named, **parts}.items():
            archive.writestr(zipfile.ZipInfo(name, TIME), data)
    return buffer.getvalue()
