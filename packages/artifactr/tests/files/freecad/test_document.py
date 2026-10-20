"""What the adapter reads of a FreeCAD document before FreeCAD starts: what it refuses, its
label, its fingerprint, and the GUI's part it puts back."""

import io
import zipfile

import pytest

from artifactr.files.app import AppFailed
from artifactr.files.freecad import fingerprint, scan
from artifactr.files.freecad.document import DEPTH, PARTS, XML_LIMIT, with_gui
from tests.files.freecad.documents import fcstd, obj, xml

LIMIT = 1 << 20


def test_a_document_of_freecads_own_types_is_scanned_for_its_label() -> None:
    kinds = ["Part::Box", "PartDesign::Body", "Sketcher::SketchObject", "Spreadsheet::Sheet"]
    objects = "".join(obj(f"O{i}", kind) for i, kind in enumerate([*kinds, "App::Origin"]))
    assert scan(fcstd(xml(objects, label="Bracket")), LIMIT).label == "Bracket"
    assert scan(fcstd(xml().replace('name="Label"', 'name="Comment"')), LIMIT).label is None


@pytest.mark.parametrize(
    ("content", "why"),
    [
        (b"", "not a zip"),
        (b"PK\x03\x04" + b"\x00" * 64, "not a zip"),
        (fcstd(**{"x.brp": "1"}).replace(b"Document.xml", b"Elsewhere.xm"), "no Document.xml"),
        (fcstd("<Document"), "isn't XML"),
        (fcstd("<Model/>"), "is a Model, not a document"),
        (fcstd('<!DOCTYPE d [<!ENTITY e "x">]><Document/>'), "declares a DTD"),
        (fcstd("<Document>" + "<a>" * DEPTH + "</a>" * DEPTH + "</Document>"), "deep"),
        (fcstd(xml(obj("Py", "App::FeaturePython"))), "holds Python: App::FeaturePython"),
        (fcstd(xml('<Object name="B"><Python value="e30=" module="Draft"/></Object>')), "Python"),
        (fcstd(xml('<Property type="App::PropertyPythonObject"/>')), "PropertyPythonObject"),
        (fcstd(xml('<XLink file="other.FCStd" name="B"/>')), "links to another file"),
        (fcstd(xml(obj("Mesh", "Mesh::Feature"))), "type that isn't allowed: Mesh::Feature"),
        (fcstd(xml(), **{"GuiDocument.xml": '<Document><Python value=""/></Document>'}), "Gui"),
    ],
    ids=[
        "empty",
        "a-broken-zip",
        "no-document",
        "not-xml",
        "another-root",
        "a-dtd",
        "too-deep",
        "a-python-feature",
        "a-proxy",
        "a-python-property",
        "an-external-link",
        "another-workbench",
        "python-in-the-gui",
    ],
)
def test_what_isnt_a_document_or_holds_python_is_refused(content: bytes, why: str) -> None:
    with pytest.raises(AppFailed, match=why) as failed:
        scan(content, LIMIT)
    assert failed.value.failure == "refused"


def test_an_internal_link_and_an_empty_one_are_kept() -> None:
    links = '<XLink file="" name="B"/><PlacementList file="PlacementList"/>'
    assert scan(fcstd(xml(obj("L", "App::Link") + links)), LIMIT).label == "Model"


def test_too_many_parts_are_refused() -> None:
    parts = {f"{index}.brp": "" for index in range(PARTS)}
    with pytest.raises(AppFailed, match=f"more than {PARTS} parts"):
        scan(fcstd(**parts), LIMIT)


def test_a_document_that_inflates_past_the_limit_is_too_large_unread() -> None:
    with pytest.raises(AppFailed, match="inflates") as failed:
        scan(fcstd(**{"Box.Shape.brp": b"0" * (LIMIT + 1)}), LIMIT)
    assert failed.value.failure == "too_large"


def test_an_xml_part_past_its_own_limit_is_too_large_however_much_is_allowed() -> None:
    padding = " " * (XML_LIMIT + 1)
    with pytest.raises(AppFailed, match=r"Document\.xml inflates") as failed:
        scan(fcstd(xml().replace("<Objects>", padding + "<Objects>")), XML_LIMIT * 2)
    assert failed.value.failure == "too_large"


def test_the_fingerprint_leaves_out_the_time_a_save_writes_and_nothing_else() -> None:
    once = fcstd(xml(modified="2026-10-20T00:00:00Z"), **{"Box.Shape.brp": "shape"})
    again = fcstd(xml(modified="2026-10-21T09:30:00Z"), **{"Box.Shape.brp": "shape"})
    assert fingerprint(once) == fingerprint(again)
    assert fingerprint(once) != fingerprint(fcstd(xml(label="Other"), **{"Box.Shape.brp": "shape"}))
    assert fingerprint(once) != fingerprint(fcstd(xml(), **{"Box.Shape.brp": "moved"}))


def test_the_gui_part_the_console_drops_is_put_back_and_the_thumbnail_isnt() -> None:
    gui = "<Document><ViewProviderData/></Document>"
    source = fcstd(xml(), **{"GuiDocument.xml": gui, "thumbnails/Thumbnail.png": b"png"})
    saved = fcstd(xml(), **{"Box.Shape.brp": "shape"})
    with zipfile.ZipFile(io.BytesIO(with_gui(saved, source))) as archive:
        assert archive.namelist() == ["Document.xml", "Box.Shape.brp", "GuiDocument.xml"]
        assert archive.read("GuiDocument.xml").decode() == gui
    assert with_gui(with_gui(saved, source), source) == with_gui(saved, source), "a fixpoint"
    assert with_gui(saved, None) == saved
    assert with_gui(saved, fcstd()) == saved
