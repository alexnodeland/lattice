"""What the adapter reads from a FreeCAD document before FreeCAD starts, and what it gives FreeCAD.

An `.FCStd` is a zip holding `Document.xml`, the objects and their properties, a part for each
shape, and, from the GUI, `GuiDocument.xml`. Opening one restores each Python feature's proxy by
importing the module it names, so [`scan`][artifactr.files.freecad.scan] reads every part,
inflating each as it goes, whatever the zip's headers say, and refuses a document that holds an
object, extension or property of a type outside the allowed sets below, which fail closed, a link
to another document, or a name or part a zip reader could take two ways. FreeCAD is never given
the bytes it was sent: it is given the zip the scan rebuilds from the parts it read, so its own
zip reader can't see what Python's didn't (native files ADR-0014).
"""

import hashlib
import io
import re
import stat
import struct
import zipfile
import zlib
from dataclasses import dataclass
from typing import Final
from xml.parsers import expat

from artifactr.files.app import AppFailed

DOCUMENT: Final = "Document.xml"
GUI: Final = "GuiDocument.xml"
THUMBNAILS: Final = "thumbnails/"
"""Where the GUI saves a thumbnail, which no fingerprint holds, since a console save drops it."""

PARTS: Final = 1_000
"""The most parts a document may hold."""

XML_LIMIT: Final = 64 << 20
"""The most bytes `Document.xml` or `GuiDocument.xml` may inflate to."""

DEPTH: Final = 256
"""The deepest an element of either may be."""

SEGMENT: Final = r"[A-Za-z0-9_](?:[A-Za-z0-9_. -]*[A-Za-z0-9_])?"
NAME: Final = re.compile(rf"{SEGMENT}(?:/{SEGMENT})*")
"""A part's name: relative segments of plain characters, none of them `.` or `..`, and none
ending in a dot or a space, which some file systems drop."""

ATTRIBUTES: Final = {
    ("Object", True): frozenset(
        {"type", "name", "id", "Extensions", "Touched", "Invalid", "Error"}
    ),
    ("ViewProvider", False): frozenset({"name", "expanded", "treeRank", "Extensions"}),
}
"""The attributes an object, or a view provider, may have, by element and whether it is in
`Document.xml`: what FreeCAD 1.1.4's `Document::Restore` reads, but `ViewType`, which names a
view provider to make."""

CAMERA: Final = re.compile(rb'(<Camera\s+settings=")[^"]*(")')
"""The GUI's camera, an Open Inventor string the GUI parses, which the scan empties."""

OBJECTS: Final = frozenset({
    "App::Line", "App::Origin", "App::Plane", "App::Point",
    "Part::Box", "Part::Cone", "Part::Cylinder", "Part::Sphere",
    "Part::Common", "Part::Cut", "Part::Fuse", "Part::Extrusion",
    "PartDesign::Body", "PartDesign::Pad",
    "Sketcher::SketchObject", "Spreadsheet::Sheet",
})  # fmt: skip
"""The object types a document may hold: those its commands and its corpus make."""

EXTENSIONS: Final = frozenset({
    "App::GeoFeatureGroupExtension", "App::OriginGroupExtension", "App::SuppressibleExtension",
    "Part::AttachExtension", "Part::PreviewExtension", "Part::PrismExtension",
})  # fmt: skip
"""The extensions an object may have."""

VIEW_EXTENSIONS: Final = frozenset({
    "Gui::ViewProviderFaceTexture", "PartGui::ViewProviderAttachExtension",
})  # fmt: skip
"""The extensions a view provider may have: those FreeCAD 1.1.4's GUI saved for a box."""

PROPERTIES: Final = frozenset({
    "App::PropertyAngle", "App::PropertyBool", "App::PropertyDistance",
    "App::PropertyEnumeration", "App::PropertyExpressionEngine", "App::PropertyFloat",
    "App::PropertyFloatConstraint", "App::PropertyInteger", "App::PropertyIntegerList",
    "App::PropertyLength", "App::PropertyLink", "App::PropertyLinkHidden",
    "App::PropertyLinkList", "App::PropertyLinkListHidden", "App::PropertyLinkSub",
    "App::PropertyLinkSubList", "App::PropertyMap", "App::PropertyMaterialList",
    "App::PropertyPlacement", "App::PropertyPrecision", "App::PropertyString",
    "App::PropertyUUID", "App::PropertyVector", "Materials::PropertyMaterial",
    "Part::PropertyGeometryList", "Part::PropertyPartShape", "Part::PropertyShapeHistory",
    "Sketcher::PropertyConstraintList", "Spreadsheet::PropertyColumnWidths",
    "Spreadsheet::PropertyRowHeights", "Spreadsheet::PropertySheet",
})  # fmt: skip
"""The property types a document's objects may have: those its commands and its corpus make.
Neither a file's, a path's, an external link's nor a Python object's is among them."""

VIEW_PROPERTIES: Final = frozenset({
    "App::PropertyAngle", "App::PropertyBool", "App::PropertyColor", "App::PropertyColorList",
    "App::PropertyDistance", "App::PropertyEnumeration", "App::PropertyFloat",
    "App::PropertyFloatConstraint", "App::PropertyInteger", "App::PropertyIntegerConstraint",
    "App::PropertyLength", "App::PropertyMaterial", "App::PropertyMaterialList",
    "App::PropertyPercent", "App::PropertyPlacement", "App::PropertyString",
    "App::PropertyVector",
})  # fmt: skip
"""The property types `GuiDocument.xml`'s view providers may have: colours, visibility and the
like, read from FreeCAD's view providers in C++; a GUI file with another is refused."""

MODIFIED: Final = re.compile(
    rb'(<Property name="LastModifiedDate"[^>]*>\s*<String value=")[^"]*(")'
)
"""Where every save writes the time, which a fingerprint leaves out."""

CHUNK: Final = 1 << 16
TIME: Final = (1980, 1, 1, 0, 0, 0)

_UNREADABLE: Final = (
    zipfile.BadZipFile,
    zlib.error,
    EOFError,
    NotImplementedError,
    RuntimeError,
    ValueError,
    OverflowError,
    struct.error,
)
"""What reading a zip that isn't one, or lies, raises: a corrupt deflate stream, an encrypted or
unknown part, sizes and offsets past what a header can hold, and a CRC that doesn't match."""


@dataclass(frozen=True)
class Scanned:
    """A document that may be opened: what FreeCAD is given, and the label it was saved with."""

    content: bytes
    """The zip rebuilt from the parts the scan read, in their order: never the bytes sent."""

    label: str | None


def scan(content: bytes, limit: int) -> Scanned:
    """Refuse what isn't a FreeCAD document, or holds what isn't allowed, and rebuild it.

    Raises:
        AppFailed: `refused` if it isn't a document, names a part twice or out of its folder,
            or holds a type, a link or a reference that isn't allowed; `too_large` if its parts
            inflate past the limit, whatever their headers say.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            parts = _named(archive.infolist())
            read: dict[str, bytes] = {}
            left = limit
            for part in parts:
                read[part.filename] = _inflated(archive, part, left)
                left -= len(read[part.filename])
    except _UNREADABLE:
        raise AppFailed("refused", "not a FreeCAD document: not a zip it can read") from None
    if DOCUMENT not in read:
        raise AppFailed("refused", f"not a FreeCAD document: no {DOCUMENT}")
    readers = [_Reader(DOCUMENT, PROPERTIES, EXTENSIONS)]
    label = readers[0].read(read[DOCUMENT])
    if GUI in read:
        readers.append(_Reader(GUI, VIEW_PROPERTIES, VIEW_EXTENSIONS))
        readers[1].read(read[GUI])
        read[GUI] = CAMERA.sub(rb"\1\2", read[GUI])
    named = {DOCUMENT, GUI}.union(*(reader.files for reader in readers))
    if unnamed := sorted(n for n in read if n not in named and not n.startswith(THUMBNAILS)):
        # A part no property names is one FreeCAD never asks for, unless it reads it as
        # something else: none is passed on.
        raise AppFailed("refused", f"not a FreeCAD document: nothing names {unnamed[0]}")
    # FreeCAD's reader takes the zip's first entry as the document, whatever it is named
    # (`Document::restore` in 1.1.4), and reads the others in the order they come, matching each
    # to a file its objects asked for: Document.xml first, then the rest as they came.
    return Scanned(_zipped({DOCUMENT: read.pop(DOCUMENT), **read}), label)


def fingerprint(content: bytes) -> str:
    """The SHA-256 of every part's name and bytes, by name, without a save's time or thumbnail.

    FreeCAD's console drops the thumbnail, so a save that changes nothing else keeps it.
    """
    digest = hashlib.sha256()
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in sorted(n for n in archive.namelist() if not n.startswith(THUMBNAILS)):
            data = archive.read(name)
            if name == DOCUMENT:
                data = MODIFIED.sub(rb"\1\2", data, count=1)
            digest.update(len(name.encode()).to_bytes(8, "big") + name.encode())
            digest.update(len(data).to_bytes(8, "big") + data)
    return digest.hexdigest()


def with_gui(saved: bytes, source: bytes | None) -> bytes:
    """The saved document, with the source's GUI part and the parts it names, as colours.

    FreeCAD's console drops them. They follow the document's own parts, as FreeCAD's GUI writes
    them. The thumbnail isn't kept, since a batch may have made it stale. The source is the
    scan's, rebuilt.
    """
    if source is None:
        return saved
    with zipfile.ZipFile(io.BytesIO(source)) as given:
        if GUI not in given.namelist():
            return saved
        reader = _Reader(GUI, VIEW_PROPERTIES, VIEW_EXTENSIONS)
        reader.read(gui := given.read(GUI))
        named = [name for name in given.namelist() if name in reader.files]
        carried = {GUI: gui, **{name: given.read(name) for name in named}}
    with zipfile.ZipFile(io.BytesIO(saved)) as made:
        parts = {name: made.read(name) for name in made.namelist() if name != GUI}
    # A part of the document's own, by the same name, is the document's.
    return _zipped({**parts, **{n: d for n, d in carried.items() if n not in parts}})


def _named(parts: list[zipfile.ZipInfo]) -> list[zipfile.ZipInfo]:
    """The parts, refused if there are too many, or one is misnamed, named twice or not a file.

    A name a zip reader could take two ways is refused: out of the folder, absolute, with a
    backslash, or another's but for case.
    """
    if len(parts) > PARTS:
        raise AppFailed("refused", f"not a FreeCAD document: more than {PARTS} parts")
    if parts and min(part.header_offset for part in parts) != 0:
        # Bytes before the first part a zip's directory names: a reader that walks the local
        # headers from the start would read a part the directory doesn't.
        raise AppFailed("refused", "not a FreeCAD document: it holds bytes before its parts")
    seen: set[str] = set()
    for part in parts:
        name = part.filename
        if not NAME.fullmatch(name) or any(s in {".", ".."} for s in name.split("/")):
            raise AppFailed("refused", f"not a FreeCAD document: a part is named {name!r}")
        if name.casefold() in seen:
            raise AppFailed("refused", f"not a FreeCAD document: {name} is named twice")
        seen.add(name.casefold())
        mode = part.external_attr >> 16
        if part.is_dir() or (stat.S_IFMT(mode) and not stat.S_ISREG(mode)):
            raise AppFailed("refused", f"not a FreeCAD document: {name} isn't a regular file")
    return parts


def _inflated(archive: zipfile.ZipFile, part: zipfile.ZipInfo, left: int) -> bytes:
    """A part's bytes, inflated a chunk at a time, refused past what is left of the limit.

    An XML part is refused past `XML_LIMIT` too, whatever its header says.
    """
    most = min(left, XML_LIMIT) if part.filename in {DOCUMENT, GUI} else left
    chunks: list[bytes] = []
    read = 0
    with archive.open(part) as stream:
        while chunk := stream.read(CHUNK):
            read += len(chunk)
            if read > most:
                raise AppFailed("too_large", f"{part.filename} inflates past {most} bytes")
            chunks.append(chunk)
    return b"".join(chunks)


def _zipped(parts: dict[str, bytes]) -> bytes:
    """A fresh zip of the parts, in order, regular files with a fixed time."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in parts.items():
            info = zipfile.ZipInfo(name, TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, data)
    return buffer.getvalue()


class _Reader:
    """Reads one XML part, refusing what isn't allowed, and the document's label."""

    def __init__(self, name: str, properties: frozenset[str], extensions: frozenset[str]) -> None:
        self.name = name
        self.properties = properties
        self.extensions = extensions
        self.path: list[tuple[str, str]] = []
        self.label: str | None = None
        self.files: set[str] = set()
        """The parts the properties name, by their `file`."""
        self.counted: dict[str, str] = {}
        self.found: dict[str, int] = {}
        self.parser = expat.ParserCreate()
        self.parser.StartDoctypeDeclHandler = self._refuse_dtd
        self.parser.EntityDeclHandler = self._refuse_dtd
        self.parser.StartElementHandler = self._start
        self.parser.EndElementHandler = self._end

    def read(self, data: bytes) -> str | None:
        try:
            self.parser.Parse(data, True)
        except expat.ExpatError as error:
            raise AppFailed("refused", f"{self.name} isn't XML: {error}") from None
        if self.counted != {tag: str(count) for tag, count in self.found.items()}:
            self._refuse("counts its objects otherwise than it lists them")
        return self.label

    def _refuse(self, why: str) -> None:
        raise AppFailed("refused", f"{self.name} {why}")

    def _refuse_dtd(self, *_: object) -> None:
        self._refuse("declares a DTD or an entity")

    def _start(self, tag: str, attributes: dict[str, str]) -> None:
        if not self.path and tag != "Document":
            self._refuse(f"is a {tag}, not a document")
        if len(self.path) >= DEPTH:
            self._refuse(f"nests elements more than {DEPTH} deep")
        if ":" in tag or any(":" in key for key in attributes):
            self._refuse(f"holds a namespaced name: {tag}")
        allowed = ATTRIBUTES.get((tag, self.name == DOCUMENT))
        if allowed is not None and (unexpected := set(attributes) - allowed):
            self._refuse(f"gives an {tag} an attribute that isn't allowed: {min(unexpected)}")
        kind = attributes.get("type", "")
        if tag == "Python":
            self._refuse("holds Python")
        if tag in {"Property", "_Property"} and kind not in self.properties:
            self._refuse(f"holds a property of a type that isn't allowed: {kind}")
        if tag == "Extension" and kind not in self.extensions:
            self._refuse(f"holds an extension of a type that isn't allowed: {kind}")
        if tag == "Object" and "type" in attributes and kind not in OBJECTS:
            self._refuse(f"holds an object of a type that isn't allowed: {kind}")
        if tag.startswith("XLink") and attributes.get("file"):
            self._refuse(f"links to another file: {attributes['file']}")
        if "file" in attributes:
            self.files.add(attributes["file"])
        if tag == "DocMap" or (tag == "XLinks" and "docs" in attributes):
            self._refuse("links to another document")
        said = attributes.get("expression", "") + attributes.get("content", "")
        # `doc#Object.Property` and `<<doc>>#Object` name another document, which FreeCAD
        # would open from disk; a `#` anywhere in an expression or a cell is refused.
        if tag in {"Expression", "Cell"} and "#" in said:
            self._refuse(f"refers to another document: {said}")
        # FreeCAD reads as many objects as each list's count says: they must be those listed.
        if tag in {"Objects", "ObjectData"} and "Count" in attributes:
            self.counted[tag] = attributes["Count"]
            self.found[tag] = 0
        if tag == "Object" and self.path and self.path[-1][0] in self.found:
            self.found[self.path[-1][0]] += 1
        # The document's own label: Document, Properties, Property name="Label", String.
        if tag == "String" and self.path[1:] == [("Properties", ""), ("Property", "Label")]:
            self.label = attributes.get("value")
        self.path.append((tag, attributes.get("name", "")))

    def _end(self, _: str) -> None:
        self.path.pop()
