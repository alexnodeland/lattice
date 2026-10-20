"""Each feature of a `.pptx`, read out of its XML into a value that two saves can be compared by.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: shapes' ids and names, the parts' names and their relationships' ids, which a save may number
again, and an attribute a save leaves to its default. The fidelity report opens and saves each
corpus file in DeckCraft and compares its feature's value before and after (lattice RFC-0003,
phase 2).
"""

import hashlib
import io
import posixpath
import zipfile
from collections.abc import Callable
from typing import Final
from xml.etree import ElementTree

from tests.files.corpus.deckcraft.make import EMU, A, P, R
from tests.files.corpus.package import PKG

Value = list[tuple[object, ...]]


def a(name: str) -> str:
    return f"{{{A}}}{name}"


def p(name: str) -> str:
    return f"{{{P}}}{name}"


class Pptx:
    """A `.pptx`'s parts, read on demand: its slides, in order, and the parts they name."""

    def __init__(self, content: bytes) -> None:
        self._zip = zipfile.ZipFile(io.BytesIO(content))

    def xml(self, name: str) -> ElementTree.Element | None:
        if name not in self._zip.namelist():
            return None
        return ElementTree.fromstring(self._zip.read(name))

    def bytes(self, name: str) -> bytes:
        return self._zip.read(name)

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
    def presentation(self) -> ElementTree.Element:
        presentation = self.xml("ppt/presentation.xml")
        assert presentation is not None, "a .pptx has a presentation"
        return presentation

    def slides(self) -> list[tuple[str, ElementTree.Element]]:
        """Each slide, in order: its part and its XML."""
        targets = self.targets("ppt/presentation.xml")
        found: list[tuple[str, ElementTree.Element]] = []
        for slide in self.presentation.iter(p("sldId")):
            part = targets[slide.get(f"{{{R}}}id", "")][1]
            xml = self.xml(part)
            assert xml is not None
            found.append((part, xml))
        return found

    def related(self, part: str, kind: str) -> list[tuple[str, ElementTree.Element]]:
        """The parts a slide's relationships of a type name, such as its `notesSlide`."""
        return [
            (target, xml)
            for found, target in self.targets(part).values()
            if found == kind and (xml := self.xml(target)) is not None
        ]


def text_of(element: ElementTree.Element) -> str:
    return "".join(t.text or "" for t in element.iter(a("t")))


def placeholder(shape: ElementTree.Element) -> str | None:
    ph = shape.find(f"{p('nvSpPr')}/{p('nvPr')}/{p('ph')}")
    return None if ph is None else ph.get("type", "body")


def texts(pptx: Pptx) -> Value:
    """Each slide's paragraphs, in order, by the placeholder they are in, if any."""
    return [
        (number, placeholder(shape), text_of(para))
        for number, (_, slide) in enumerate(pptx.slides(), 1)
        for shape in slide.iter(p("sp"))
        for para in shape.iter(a("p"))
        if text_of(para)
    ]


def slides(pptx: Pptx) -> Value:
    """Each slide's title, and whether it is shown."""
    return [
        (
            next((text_of(s) for s in slide.iter(p("sp")) if placeholder(s) == "title"), ""),
            slide.get("show", "1") in ("1", "true"),
        )
        for _, slide in pptx.slides()
    ]


def text_formatting(pptx: Pptx) -> Value:
    """Each run's bold, italics, underline, size and colour."""
    found: Value = []
    for _, slide in pptx.slides():
        for r in slide.iter(a("r")):
            props = r.find(a("rPr"))
            color = None if props is None else props.find(f"{a('solidFill')}/{a('srgbClr')}")
            attributes = {} if props is None else props.attrib
            found.append(
                (
                    text_of(r),
                    attributes.get("b", "0") in ("1", "true"),
                    attributes.get("i", "0") in ("1", "true"),
                    attributes.get("u", "none"),
                    attributes.get("sz"),
                    None if color is None else color.get("val"),
                )
            )
    return found


def bullets(pptx: Pptx) -> Value:
    """Each paragraph's level, from 0, and its text."""
    found: Value = []
    for _, slide in pptx.slides():
        for para in slide.iter(a("p")):
            props = para.find(a("pPr"))
            found.append((int("0" if props is None else props.get("lvl", "0")), text_of(para)))
    return [f for f in found if f[1]]


def notes(pptx: Pptx) -> Value:
    """Each slide's notes: the words of its notes slide's body placeholder."""
    return [
        (number, text_of(shape))
        for number, (part, _) in enumerate(pptx.slides(), 1)
        for _, notes in pptx.related(part, "notesSlide")
        for shape in notes.iter(p("sp"))
        if placeholder(shape) == "body"
    ]


def tables(pptx: Pptx) -> Value:
    return [
        tuple(tuple(text_of(cell) for cell in row.iter(a("tc"))) for row in table.iter(a("tr")))
        for _, slide in pptx.slides()
        for table in slide.iter(a("tbl"))
    ]


def place(element: ElementTree.Element) -> tuple[int, int, int, int] | None:
    """A shape's place and size, in points, from its transform."""
    off, ext = element.find(f".//{a('off')}"), element.find(f".//{a('ext')}")
    if off is None or ext is None:
        return None
    return (
        int(off.get("x", "0")) // EMU,
        int(off.get("y", "0")) // EMU,
        int(ext.get("cx", "0")) // EMU,
        int(ext.get("cy", "0")) // EMU,
    )


def images(pptx: Pptx) -> Value:
    """Each picture's bytes, by digest, its place, and its description."""
    found: Value = []
    for part, slide in pptx.slides():
        targets = pptx.targets(part)
        for picture in slide.iter(p("pic")):
            blip = picture.find(f".//{a('blip')}")
            described = picture.find(f".//{p('cNvPr')}")
            if blip is None:
                continue
            data = pptx.bytes(targets[blip.get(f"{{{R}}}embed", "")][1])
            found.append(
                (
                    hashlib.sha256(data).hexdigest(),
                    place(picture),
                    None if described is None else described.get("descr"),
                )
            )
    return found


def shapes(pptx: Pptx) -> Value:
    """Each drawn shape's geometry, fill and place."""
    found: Value = []
    for _, slide in pptx.slides():
        for shape in slide.iter(p("sp")):
            props = shape.find(p("spPr"))
            geometry = None if props is None else props.find(a("prstGeom"))
            if props is None or geometry is None:
                continue
            fill = props.find(f"{a('solidFill')}/{a('srgbClr')}")
            found.append(
                (geometry.get("prst"), None if fill is None else fill.get("val"), place(props))
            )
    return found


def transitions(pptx: Pptx) -> Value:
    """Each slide's transition: its effect and speed, once, though a save may write it twice,
    as a choice of markup and its fallback."""
    found: Value = []
    for number, (_, slide) in enumerate(pptx.slides(), 1):
        written = (
            (number, tuple(child.tag.split("}")[1] for child in t), t.get("spd", "fast"))
            for t in slide.iter(p("transition"))
        )
        found += dict.fromkeys(written)
    return found


def hyperlinks(pptx: Pptx) -> Value:
    """Each linked run's words and where its link goes."""
    found: Value = []
    for part, slide in pptx.slides():
        targets = pptx.targets(part)
        for r in slide.iter(a("r")):
            link = r.find(f"{a('rPr')}/{a('hlinkClick')}")
            if link is not None:
                found.append((text_of(r), targets[link.get(f"{{{R}}}id", "")][1]))
    return found


def slide_size(pptx: Pptx) -> Value:
    size = pptx.presentation.find(p("sldSz"))
    assert size is not None
    return [(int(size.get("cx", "0")) // EMU, int(size.get("cy", "0")) // EMU)]


def comments(pptx: Pptx) -> Value:
    """Each comment's slide, author and words, by its author's name, not their id."""
    authors_part = next(
        (
            target
            for kind, target in pptx.targets("ppt/presentation.xml").values()
            if kind == "commentAuthors"
        ),
        "",
    )
    authors_xml = pptx.xml(authors_part)
    authors = {
        author.get("id"): author.get("name")
        for author in ([] if authors_xml is None else authors_xml.iter(p("cmAuthor")))
    }
    return [
        (number, authors.get(comment.get("authorId")), text_of_comment(comment))
        for number, (part, _) in enumerate(pptx.slides(), 1)
        for _, listed in pptx.related(part, "comments")
        for comment in listed.iter(p("cm"))
    ]


def text_of_comment(comment: ElementTree.Element) -> str:
    words = comment.find(p("text"))
    return "" if words is None else words.text or ""


READERS: Final[dict[str, Callable[[Pptx], Value]]] = {
    "text": texts,
    "slides": slides,
    "text_formatting": text_formatting,
    "bullets": bullets,
    "notes": notes,
    "tables": tables,
    "images": images,
    "shapes": shapes,
    "transitions": transitions,
    "hyperlinks": hyperlinks,
    "slide_size": slide_size,
    "comments": comments,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a `.pptx`."""
    return READERS[feature](Pptx(content))
