"""FreeCAD's corpus: what each feature's value means, and what each hostile file is."""

import io
import zipfile

from artifactr.files.freecad.document import XML_LIMIT
from tests.files.corpus.freecad.corpus import CORPUS
from tests.files.corpus.freecad.features import READERS, Value, read


def value(feature: str) -> Value:
    return read(feature, CORPUS.source(feature))


def test_a_features_value_is_what_it_means() -> None:
    assert value("booleans")[2:] == [
        ("Cut", "Part::Cut", "Box", "Cylinder"),
        ("Sphere", "Part::Sphere", None, None),
        ("Fusion", "Part::Fuse", "Cut", "Sphere"),
    ]
    assert value("spreadsheet") == [
        ("Spreadsheet", "A1", "'Length", None),
        ("Spreadsheet", "B1", "42", "length"),
        ("Spreadsheet", "B2", "=B1 * 2", None),
    ]
    assert value("expressions")[3:] == [
        ("Box", "Length", "Spreadsheet.length"),
        ("Box", "Width", "Length / 2"),
    ]
    assert value("placement") == [("Box", (1.0, 2.0, 3.0, 0.0, 0.0, 0.258819, 0.965926))]
    assert value("gui") == [("Box", "Hidden box"), ("Box", "false")]
    assert ("Pad", "Sketch", (("Length", 3.0),)) in value("part_design")


def test_every_feature_has_a_reader_and_is_made_by_freecad() -> None:
    assert set(READERS) == set(CORPUS.makers)
    assert CORPUS.made_by_app


def parts(name: str) -> dict[str, int]:
    with zipfile.ZipFile(io.BytesIO(CORPUS.hostile_file(name))) as archive:
        return {info.filename: info.file_size for info in archive.infolist()}


def document(name: str) -> bytes:
    with zipfile.ZipFile(io.BytesIO(CORPUS.hostile_file(name))) as archive:
        return archive.read("Document.xml")


def test_each_hostile_file_is_a_document_broken_or_bearing_python() -> None:
    assert parts("zip_bomb") == {"Box.Shape.brp": 1 << 30}
    assert parts("huge_document")["Document.xml"] > XML_LIMIT
    assert document("deep_nesting").count(b"<a>") == 100_000
    assert b"<!ENTITY e SYSTEM" in document("entity")
    assert b'encoded="yes"/>' in document("pickled_proxy")
    assert b'module="Draft"' in document("freecad_module_proxy")
    assert list(parts("gui_proxy")).count("GuiDocument.xml") == 1
    assert b'XLink file="/etc/passwd"' in document("external_link")
    assert document("cycle").count(b'<Link value="Fusion"/>') == 1
