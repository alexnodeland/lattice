"""What the adapter reads of a FreeCAD document before FreeCAD starts: what it refuses, its
label, the zip it rebuilds, its fingerprint, and the GUI's part it puts back."""

import io
import stat
import warnings
import zipfile

import pytest

from artifactr.files.app import AppFailed
from artifactr.files.freecad import fingerprint, scan
from artifactr.files.freecad.document import DEPTH, PARTS, XML_LIMIT, with_gui
from tests.files.freecad.documents import TIME, fcstd, obj, xml

LIMIT = 1 << 20


def prop(kind: str, inner: str = "") -> str:
    """An object with one property of a type, holding `inner`."""
    held = f'<Property name="P" type="{kind}">{inner}</Property>'
    return f'<Object name="Box"><Properties>{held}</Properties></Object>'


def part(element: str) -> bytes:
    """A document with `element` among its objects."""
    return fcstd(xml(element))


def test_a_document_of_the_allowed_types_is_scanned_for_its_label() -> None:
    kinds = ["Part::Box", "PartDesign::Body", "Sketcher::SketchObject", "Spreadsheet::Sheet"]
    objects = "".join(obj(f"O{i}", kind) for i, kind in enumerate([*kinds, "App::Origin"]))
    assert scan(fcstd(xml(objects, label="Bracket")), LIMIT).label == "Bracket"
    assert scan(fcstd(xml().replace('name="Label"', 'name="Comment"')), LIMIT).label is None


def test_what_freecad_is_given_is_the_zip_the_scan_rebuilds() -> None:
    source = fcstd(xml(), **{"Box.Shape.brp": "shape"})
    scanned = scan(source + b"trailing junk", LIMIT)
    with zipfile.ZipFile(io.BytesIO(scanned.content)) as archive:
        assert archive.namelist() == ["Document.xml", "Box.Shape.brp"]
        assert archive.read("Box.Shape.brp") == b"shape"
        assert all(stat.S_ISREG(info.external_attr >> 16) for info in archive.infolist())
    assert fingerprint(scanned.content) == fingerprint(source)


def duplicated() -> bytes:
    buffer = io.BytesIO()
    with warnings.catch_warnings(), zipfile.ZipFile(buffer, "w") as archive:
        warnings.simplefilter("ignore")
        archive.writestr("Document.xml", xml())
        archive.writestr("Document.xml", xml(obj("Py", "App::FeaturePython")))
    return buffer.getvalue()


def linked() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("Document.xml", xml())
        info = zipfile.ZipInfo("Box.Shape.brp", TIME)
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "/etc/passwd")
    return buffer.getvalue()


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
        (part(obj("Py", "App::FeaturePython")), "allowed: App::FeaturePython"),
        (part(obj("Mesh", "Mesh::Feature")), "allowed: Mesh::Feature"),
        (part('<Object name="B"><Python value="e30=" module="Draft"/></Object>'), "Python"),
        (part(prop("App::PropertyPythonObject")), "PropertyPythonObject"),
        (part(prop("App::PropertyFileIncluded", '<FileIncluded file=""/>')), "FileIncluded"),
        (part(prop("App::PropertyPath")), "PropertyPath"),
        (part(prop("App::PropertyPersistentObject")), "PersistentObject"),
        (part(prop("App::PropertyXLink", '<XLink file="o.FCStd" name="B"/>')), "XLink"),
        (part('<Extensions><Extension type="App::LinkExtension"/></Extensions>'), "extension"),
        (part(prop("App::PropertyLink", '<XLink file="/etc/passwd" name="B"/>')), "another file"),
        (part('<XLinks count="1" docs="1"><DocMap index="0"/></XLinks>'), "another document"),
        (part('<Expression path="Length" expression="other#Box.Length"/>'), "another document"),
        (part('<Cell address="A1" content="=&lt;&lt;o&gt;&gt;#Box.Length"/>'), "another document"),
        (part("<x:a xmlns:x='u'/>"), "namespaced"),
        (fcstd(xml().replace("<Objects>", '<Objects Count="2">')), "counts its objects"),
        (fcstd(xml(), **{"GuiDocument.xml": '<Document><Python value=""/></Document>'}), "Gui"),
        (fcstd(xml(obj("Py", "App::FeaturePython"))) + fcstd(), "bytes before its parts"),
        (duplicated(), "named twice"),
        (fcstd(**{"document.XML": "x", "Document.xml": xml()}), "named twice"),
        (fcstd(**{"../evil.brp": "x"}), "named '../evil.brp'"),
        (fcstd(**{"/evil.brp": "x"}), "named '/evil.brp'"),
        (fcstd(**{"./evil.brp": "x"}), "named './evil.brp'"),
        (fcstd(**{"a\\evil.brp": "x"}), "evil.brp'"),
        (fcstd(**{"shapes/": ""}), "named .shapes/."),
        (linked(), "isn't a regular file"),
    ],
    ids=[
        "empty", "a-broken-zip", "no-document", "not-xml", "another-root", "a-dtd", "too-deep",
        "a-python-feature", "another-workbench", "a-proxy", "a-python-property", "an-included-file",
        "a-path", "a-persistent-object", "an-xlink-property", "an-extension", "an-external-link",
        "a-document-map", "a-cross-document-expression", "a-cross-document-cell", "a-namespace",
        "a-lying-count", "python-in-the-gui", "a-prefix", "a-duplicate-document", "a-case-variant",
        "zip-slip", "an-absolute-name", "a-dot-name", "a-backslash", "a-folder", "a-symlink",
    ],
)  # fmt: skip
def test_what_isnt_a_document_or_isnt_allowed_is_refused(content: bytes, why: str) -> None:
    with pytest.raises(AppFailed, match=why) as failed:
        scan(content, LIMIT)
    assert failed.value.failure == "refused"


def test_an_internal_link_and_an_empty_one_are_kept() -> None:
    links = '<XLink file="" name="B"/><PlacementList file="PlacementList"/>'
    assert scan(fcstd(xml(obj("L", "App::Origin") + links)), LIMIT).label == "Model"


def test_too_many_parts_are_refused() -> None:
    parts = {f"{index}.brp": "" for index in range(PARTS)}
    with pytest.raises(AppFailed, match=f"more than {PARTS} parts"):
        scan(fcstd(**parts), LIMIT)


def test_a_document_that_inflates_past_the_limit_is_too_large() -> None:
    with pytest.raises(AppFailed, match="inflates") as failed:
        scan(fcstd(**{"Box.Shape.brp": b"0" * (LIMIT + 1)}), LIMIT)
    assert failed.value.failure == "too_large"


def test_a_part_whose_header_understates_its_size_is_refused_not_trusted() -> None:
    honest = fcstd(**{"Box.Shape.brp": b"0" * 4096})
    with zipfile.ZipFile(io.BytesIO(honest)) as archive:
        info = archive.getinfo("Box.Shape.brp")
    size = info.file_size.to_bytes(4, "little")
    lying = honest.replace(size, (16).to_bytes(4, "little"))
    with pytest.raises(AppFailed, match="not a zip it can read"):
        scan(lying, LIMIT)


def test_an_xml_part_past_its_own_limit_is_too_large_however_much_is_allowed() -> None:
    padding = " " * (XML_LIMIT + 1)
    with pytest.raises(AppFailed, match=r"Document\.xml inflates") as failed:
        scan(fcstd(xml().replace("<Objects>", padding + "<Objects>")), XML_LIMIT * 2)
    assert failed.value.failure == "too_large"


def test_the_fingerprint_leaves_out_the_time_a_save_writes_and_the_thumbnail() -> None:
    once = fcstd(xml(modified="2026-10-20T00:00:00Z"), **{"Box.Shape.brp": "shape"})
    again = fcstd(xml(modified="2026-10-21T09:30:00Z"), **{"Box.Shape.brp": "shape"})
    assert fingerprint(once) == fingerprint(again)
    assert fingerprint(once) != fingerprint(fcstd(xml(label="Other"), **{"Box.Shape.brp": "shape"}))
    assert fingerprint(once) != fingerprint(fcstd(xml(), **{"Box.Shape.brp": "moved"}))


def test_a_no_op_save_of_a_gui_made_file_keeps_its_fingerprint() -> None:
    """The GUI writes a thumbnail and its part, in its own order; the console drops both."""
    gui = "<Document><ViewProviderData/></Document>"
    made = fcstd(
        xml(), **{"GuiDocument.xml": gui, "thumbnails/Thumbnail.png": b"png", "Box.Shape.brp": "s"}
    )
    saved = fcstd(xml(modified="2026-10-21T00:00:00Z"), **{"Box.Shape.brp": "s"})
    assert fingerprint(with_gui(saved, scan(made, LIMIT).content)) == fingerprint(made)


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


def test_a_list_counted_as_freecad_counts_it_is_read() -> None:
    counted = xml(obj("Box", "Part::Box")).replace("<Objects>", '<Objects Count="1">')
    assert scan(fcstd(counted), LIMIT).label == "Model"
