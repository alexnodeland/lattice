"""Each feature of a `.docx`, read out of its XML into a value that two saves can be compared by.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: ids that are numbered again, the order of attributes, the time a change was tracked. The
fidelity report opens and saves each corpus file in WordCraft and compares its feature's value
before and after (lattice RFC-0003, phase 2).
"""

import hashlib
import io
import posixpath
import zipfile
from collections.abc import Callable
from typing import Final
from xml.etree import ElementTree

from tests.files.corpus.wordcraft.make import PKG, WP, A, R, W

Value = list[tuple[object, ...]]


def q(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def w(name: str) -> str:
    return q(W, name)


class Docx:
    """A `.docx`'s parts, read on demand: its XML, and the targets its document's rels name."""

    def __init__(self, content: bytes) -> None:
        self._zip = zipfile.ZipFile(io.BytesIO(content))

    def xml(self, name: str) -> ElementTree.Element | None:
        if name not in self._zip.namelist():
            return None
        return ElementTree.fromstring(self._zip.read(name))

    def bytes(self, name: str) -> bytes:
        return self._zip.read(name)

    @property
    def document(self) -> ElementTree.Element:
        document = self.xml("word/document.xml")
        assert document is not None, "a .docx has a document"
        return document

    def targets(self) -> dict[str, str]:
        """The document's relationships: id to the part it names, from the zip's root."""
        rels = self.xml("word/_rels/document.xml.rels")
        found: dict[str, str] = {}
        for rel in [] if rels is None else rels.iter(q(PKG, "Relationship")):
            target = rel.get("Target", "")
            found[rel.get("Id", "")] = posixpath.normpath(posixpath.join("word", target))
        return found

    def part(self, kind: str) -> ElementTree.Element | None:
        """The part a relationship of a type names, such as `comments`, by its rels."""
        rels = self.xml("word/_rels/document.xml.rels")
        for rel in [] if rels is None else rels.iter(q(PKG, "Relationship")):
            if rel.get("Type", "").endswith(f"/{kind}"):
                return self.xml(posixpath.normpath(posixpath.join("word", rel.get("Target", ""))))
        return None


def text_of(element: ElementTree.Element) -> str:
    return "".join(t.text or "" for t in element.iter() if t.tag in (w("t"), w("delText")))


def paragraphs(docx: Docx) -> list[ElementTree.Element]:
    body = docx.document.find(w("body"))
    assert body is not None
    return list(body.iter(w("p")))


def text(docx: Docx) -> Value:
    return [(text_of(e),) for e in paragraphs(docx) if text_of(e)]


def styles(docx: Docx) -> Value:
    """Each paragraph's style, by its name, which a save may give another id."""
    names: dict[str, str] = {}
    defined = docx.part("styles")
    for style in [] if defined is None else defined.iter(w("style")):
        name = style.find(w("name"))
        names[style.get(w("styleId"), "")] = (
            name.get(w("val"), "") if name is not None else ""
        ).lower()
    found: Value = []
    for e in paragraphs(docx):
        style = e.find(f"{w('pPr')}/{w('pStyle')}")
        sid = "Normal" if style is None else style.get(w("val"), "")
        found.append((names.get(sid, sid.lower()), text_of(e)))
    return [f for f in found if f[1]]


def run_properties(docx: Docx) -> Value:
    found: Value = []
    for run in docx.document.iter(w("r")):
        props = run.find(w("rPr"))
        if props is None or not text_of(run):
            continue
        kept = sorted(
            (child.tag.split("}")[1], child.get(w("val"), "on"))
            for child in props
            if child.tag.split("}")[1] in {"b", "i", "u", "color", "sz", "strike"}
        )
        found.append((text_of(run), tuple(kept)))
    return found


def tables(docx: Docx) -> Value:
    return [
        tuple(tuple(text_of(cell) for cell in row.iter(w("tc"))) for row in table.iter(w("tr")))
        for table in docx.document.iter(w("tbl"))
    ]


def lists(docx: Docx) -> Value:
    """Each item's format, level and text: numbering ids a save may number again."""
    numbering = docx.part("numbering")
    abstract: dict[str, dict[str, str]] = {}
    nums: dict[str, str] = {}
    for definition in [] if numbering is None else numbering.iter(w("abstractNum")):
        levels = {
            lvl.get(w("ilvl"), ""): fmt.get(w("val"), "")
            for lvl in definition.iter(w("lvl"))
            if (fmt := lvl.find(w("numFmt"))) is not None
        }
        abstract[definition.get(w("abstractNumId"), "")] = levels
    for num in [] if numbering is None else numbering.iter(w("num")):
        ref = num.find(w("abstractNumId"))
        nums[num.get(w("numId"), "")] = "" if ref is None else ref.get(w("val"), "")
    found: Value = []
    for e in paragraphs(docx):
        props = e.find(f"{w('pPr')}/{w('numPr')}")
        if props is None:
            continue
        ilvl, num = props.find(w("ilvl")), props.find(w("numId"))
        level = "0" if ilvl is None else ilvl.get(w("val"), "0")
        numbered = "" if num is None else num.get(w("val"), "")
        fmt = abstract.get(nums.get(numbered, ""), {}).get(level, "")
        found.append((fmt, int(level), text_of(e)))
    return found


def images(docx: Docx) -> Value:
    """Each picture's bytes, by digest, and its size on the page."""
    targets = docx.targets()
    found: Value = []
    for drawing in docx.document.iter(w("drawing")):
        extent = drawing.find(f".//{q(WP, 'extent')}")
        blip = drawing.find(f".//{q(A, 'blip')}")
        if extent is None or blip is None:
            continue
        data = docx.bytes(targets[blip.get(q(R, "embed"), "")])
        found.append((hashlib.sha256(data).hexdigest(), extent.get("cx"), extent.get("cy")))
    return found


def headers_and_footers(docx: Docx) -> Value:
    targets = docx.targets()
    found: Value = []
    for kind in ("header", "footer"):
        for ref in docx.document.iter(w(f"{kind}Reference")):
            part = docx.xml(targets[ref.get(q(R, "id"), "")])
            found.append((kind, ref.get(w("type")), "" if part is None else text_of(part)))
    return sorted(found, key=repr)


def footnotes(docx: Docx) -> Value:
    notes = docx.part("footnotes")
    return [
        (text_of(note).strip(),)
        for note in ([] if notes is None else notes.iter(w("footnote")))
        if note.get(w("type")) is None
    ]


def comments(docx: Docx) -> Value:
    """Each comment's author and words, and the words it is anchored on."""
    notes = docx.part("comments")
    anchored: dict[str, str] = {}
    for e in paragraphs(docx):
        opened: str | None = None
        for child in e:
            if child.tag == w("commentRangeStart"):
                opened = child.get(w("id"), "")
                anchored.setdefault(opened, "")
            elif child.tag == w("commentRangeEnd"):
                opened = None
            elif opened is not None:
                anchored[opened] += text_of(child)
    return [
        (note.get(w("author")), text_of(note), anchored.get(note.get(w("id"), ""), ""))
        for note in ([] if notes is None else notes.iter(w("comment")))
    ]


def tracked_changes(docx: Docx) -> Value:
    return [
        (change.tag.split("}")[1], change.get(w("author")), text_of(change))
        for change in docx.document.iter()
        if change.tag in (w("ins"), w("del"))
    ]


def sections(docx: Docx) -> Value:
    found: Value = []
    for section in docx.document.iter(w("sectPr")):
        size, margins, cols = (
            section.find(w("pgSz")),
            section.find(w("pgMar")),
            section.find(w("cols")),
        )
        found.append(
            (
                None
                if size is None
                else (size.get(w("w")), size.get(w("h")), size.get(w("orient"))),
                None
                if margins is None
                else tuple(margins.get(w(side)) for side in ("top", "right", "bottom", "left")),
                "1" if cols is None else cols.get(w("num"), "1"),
            )
        )
    return found


READERS: Final[dict[str, Callable[[Docx], Value]]] = {
    "text": text,
    "styles": styles,
    "run_properties": run_properties,
    "tables": tables,
    "lists": lists,
    "images": images,
    "headers_and_footers": headers_and_footers,
    "footnotes": footnotes,
    "comments": comments,
    "tracked_changes": tracked_changes,
    "sections": sections,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a `.docx`."""
    return READERS[feature](Docx(content))
