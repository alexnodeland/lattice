"""Each feature of a `.xlsx`, read out of its XML into a value that two saves can be compared by.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: the order of the shared strings and of the styles, which a save may number again, a
formula's cached value, which GridCraft computes, and an attribute a save leaves to its default.
The fidelity report opens and saves each corpus file in GridCraft and compares its feature's
value before and after (lattice RFC-0003, phase 2).
"""

import io
import posixpath
import zipfile
from collections.abc import Callable
from typing import Final
from xml.etree import ElementTree

from tests.files.corpus.gridcraft.make import R, S
from tests.files.corpus.package import PKG

Value = list[tuple[object, ...]]

BUILTIN: Final = {"0": "General", "10": "0.00%", "14": "m/d/yyyy"}
"""The built-in number formats the corpus uses, by id, as the schema numbers them."""


def s(name: str) -> str:
    return f"{{{S}}}{name}"


class Xlsx:
    """A `.xlsx`'s parts, read on demand: its sheets, by name, and what they share."""

    def __init__(self, content: bytes) -> None:
        self._zip = zipfile.ZipFile(io.BytesIO(content))

    def xml(self, name: str) -> ElementTree.Element | None:
        if name not in self._zip.namelist():
            return None
        return ElementTree.fromstring(self._zip.read(name))

    def targets(self, part: str) -> dict[str, tuple[str, str]]:
        """A part's relationships: id to its type and the part it names, or its external URL."""
        folder, name = posixpath.split(part)
        rels = self.xml(posixpath.join(folder, "_rels", f"{name}.rels"))
        found: dict[str, tuple[str, str]] = {}
        for rel in [] if rels is None else rels.iter(f"{{{PKG}}}Relationship"):
            target = rel.get("Target", "")
            if rel.get("TargetMode") != "External":
                target = posixpath.normpath(posixpath.join(folder, target))
            found[rel.get("Id", "")] = (rel.get("Type", "").rsplit("/", 1)[-1], target)
        return found

    @property
    def workbook(self) -> ElementTree.Element:
        workbook = self.xml("xl/workbook.xml")
        assert workbook is not None, "a .xlsx has a workbook"
        return workbook

    def sheets(self) -> list[tuple[str, str, ElementTree.Element]]:
        """Each sheet, in order: its name, its part, and its XML."""
        targets = self.targets("xl/workbook.xml")
        found: list[tuple[str, str, ElementTree.Element]] = []
        for sheet in self.workbook.iter(s("sheet")):
            part = targets[sheet.get(f"{{{R}}}id", "")][1]
            xml = self.xml(part)
            assert xml is not None
            found.append((sheet.get("name", ""), part, xml))
        return found

    def strings(self) -> list[str]:
        shared = self.xml("xl/sharedStrings.xml")
        return [text_of(item) for item in ([] if shared is None else shared.iter(s("si")))]

    def styles(self) -> ElementTree.Element:
        styles = self.xml("xl/styles.xml")
        assert styles is not None, "the corpus' files have styles"
        return styles

    def related(self, part: str, kind: str) -> list[ElementTree.Element]:
        """The parts a sheet's relationships of a type name, such as its `comments`."""
        return [
            xml
            for found, target in self.targets(part).values()
            if found == kind and (xml := self.xml(target)) is not None
        ]


def text_of(element: ElementTree.Element) -> str:
    return "".join(t.text or "" for t in element.iter(s("t")))


def cells(xlsx: Xlsx) -> list[tuple[str, str, ElementTree.Element]]:
    """Every cell that holds something: its sheet, its reference and its XML."""
    return [
        (name, c.get("r", ""), c)
        for name, _, sheet in xlsx.sheets()
        for c in sheet.iter(s("c"))
        if c.find(s("v")) is not None or c.find(s("f")) is not None or c.find(s("is")) is not None
    ]


def value_of(c: ElementTree.Element, strings: list[str]) -> object:
    """A cell's value: its text, wherever it is kept, its number, or its boolean."""
    kind, v = c.get("t", "n"), c.find(s("v"))
    raw = "" if v is None else v.text or ""
    if kind == "s":
        return strings[int(raw)]
    if kind == "inlineStr":
        inline = c.find(s("is"))
        return "" if inline is None else text_of(inline)
    if kind == "b":
        return raw == "1"
    return raw if kind == "str" else float(raw)


def values(xlsx: Xlsx) -> Value:
    strings = xlsx.strings()
    return [
        (name, ref, value_of(c, strings)) for name, ref, c in cells(xlsx) if c.find(s("f")) is None
    ]


def formulas(xlsx: Xlsx) -> Value:
    return [
        (name, ref, f.text) for name, ref, c in cells(xlsx) if (f := c.find(s("f"))) is not None
    ]


def style_of(xlsx: Xlsx, c: ElementTree.Element) -> ElementTree.Element | None:
    xfs = xlsx.styles().find(s("cellXfs"))
    return None if xfs is None else list(xfs)[int(c.get("s", "0"))]


def number_formats(xlsx: Xlsx) -> Value:
    """Each cell's number format, by its code, which a save may give another id."""
    codes = dict(BUILTIN)
    for fmt in xlsx.styles().iter(s("numFmt")):
        codes[fmt.get("numFmtId", "")] = fmt.get("formatCode", "")
    found: Value = []
    for name, ref, c in cells(xlsx):
        xf = style_of(xlsx, c)
        found.append((name, ref, codes.get("0" if xf is None else xf.get("numFmtId", "0"))))
    return found


def fonts_and_fills(xlsx: Xlsx) -> Value:
    """Each cell's bold, italics, colour and fill, by what they are, not by their ids."""
    fonts = list(xlsx.styles().iter(s("font")))
    fills = list(xlsx.styles().iter(s("fill")))
    found: Value = []
    for name, ref, c in cells(xlsx):
        xf = style_of(xlsx, c)
        font = fonts[int("0" if xf is None else xf.get("fontId", "0"))]
        fill = fills[int("0" if xf is None else xf.get("fillId", "0"))]
        color, solid = font.find(s("color")), fill.find(f"{s('patternFill')}/{s('fgColor')}")
        found.append(
            (
                name,
                ref,
                font.find(s("b")) is not None,
                font.find(s("i")) is not None,
                None if color is None else color.get("rgb"),
                None if solid is None else solid.get("rgb"),
            )
        )
    return found


def sheets(xlsx: Xlsx) -> Value:
    return [
        (sheet.get("name"), sheet.get("state", "visible"))
        for sheet in xlsx.workbook.iter(s("sheet"))
    ]


def merges(xlsx: Xlsx) -> Value:
    return [
        (name, merge.get("ref"))
        for name, _, sheet in xlsx.sheets()
        for merge in sheet.iter(s("mergeCell"))
    ]


def sizes(xlsx: Xlsx) -> Value:
    """Each custom column's width, to a tenth of a character, as a save may round it to a pixel,
    and each custom row's height."""
    found: Value = []
    for name, _, sheet in xlsx.sheets():
        found += [
            ("col", name, col.get("min"), col.get("max"), round(float(col.get("width", "0")), 1))
            for col in sheet.iter(s("col"))
            if col.get("customWidth") in ("1", "true")
        ]
        found += [
            ("row", name, r.get("r"), float(r.get("ht", "0")))
            for r in sheet.iter(s("row"))
            if r.get("customHeight") in ("1", "true")
        ]
    return found


def freeze_panes(xlsx: Xlsx) -> Value:
    return [
        (name, pane.get("xSplit"), pane.get("ySplit"), pane.get("topLeftCell"), pane.get("state"))
        for name, _, sheet in xlsx.sheets()
        for pane in sheet.iter(s("pane"))
    ]


def defined_names(xlsx: Xlsx) -> Value:
    return sorted((name.get("name"), name.text) for name in xlsx.workbook.iter(s("definedName")))


def comments(xlsx: Xlsx) -> Value:
    """Each note's cell, author and words."""
    found: Value = []
    for name, part, _ in xlsx.sheets():
        for notes in xlsx.related(part, "comments"):
            authors = [text_of(a) or a.text or "" for a in notes.iter(s("author"))]
            found += [
                (name, note.get("ref"), authors[int(note.get("authorId", "0"))], text_of(note))
                for note in notes.iter(s("comment"))
            ]
    return found


def data_validation(xlsx: Xlsx) -> Value:
    found: Value = []
    for name, _, sheet in xlsx.sheets():
        for rule in sheet.iter(s("dataValidation")):
            limits = tuple(f.text for f in rule if f.tag in (s("formula1"), s("formula2")))
            operator = rule.get("operator", "between")  # the schema's default
            found.append((name, rule.get("sqref"), rule.get("type"), operator, limits))
    return found


def conditional_formatting(xlsx: Xlsx) -> Value:
    found: Value = []
    for name, _, sheet in xlsx.sheets():
        for formatted in sheet.iter(s("conditionalFormatting")):
            found += [
                (
                    name,
                    formatted.get("sqref"),
                    rule.get("type"),
                    rule.get("operator"),
                    tuple(f.text for f in rule.iter(s("formula"))),
                )
                for rule in formatted.iter(s("cfRule"))
            ]
    return found


def tables(xlsx: Xlsx) -> Value:
    return [
        (
            name,
            table.get("name"),
            table.get("ref"),
            tuple(column.get("name") for column in table.iter(s("tableColumn"))),
        )
        for name, part, _ in xlsx.sheets()
        for table in xlsx.related(part, "table")
    ]


def hyperlinks(xlsx: Xlsx) -> Value:
    """Each link's cell and where it goes: a URL, by its relationship, or a place in the book."""
    found: Value = []
    for name, part, sheet in xlsx.sheets():
        targets = xlsx.targets(part)
        for link in sheet.iter(s("hyperlink")):
            rid = link.get(f"{{{R}}}id")
            found.append((name, link.get("ref"), targets[rid][1] if rid else link.get("location")))
    return found


READERS: Final[dict[str, Callable[[Xlsx], Value]]] = {
    "values": values,
    "formulas": formulas,
    "number_formats": number_formats,
    "fonts_and_fills": fonts_and_fills,
    "sheets": sheets,
    "merges": merges,
    "sizes": sizes,
    "freeze_panes": freeze_panes,
    "defined_names": defined_names,
    "comments": comments,
    "data_validation": data_validation,
    "conditional_formatting": conditional_formatting,
    "tables": tables,
    "hyperlinks": hyperlinks,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a `.xlsx`."""
    return READERS[feature](Xlsx(content))
