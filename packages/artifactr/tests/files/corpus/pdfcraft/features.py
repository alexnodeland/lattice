"""Each feature of a `.pdf`, read out of its objects into a value two saves can be compared by.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: objects' numbers, which a save renumbers, so a page is named by its place in the document;
how a stream is compressed, so a stream is read inflated; and an entry a save leaves to its
default. The fidelity report opens and saves each corpus file in PdfCraft and compares its
feature's value before and after (lattice RFC-0003, phase 2).
"""

import hashlib
import re
import zlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final

Value = list[tuple[object, ...]]

HEADER: Final = re.compile(rb"(?<!\d)(\d+)\s+(\d+)\s+obj\b")
STREAM: Final = re.compile(rb"\s*stream\r?\n")
TOKEN: Final = re.compile(
    rb"\s*(?:(?P<open><<)|(?P<close>>>)|(?P<start>\[)|(?P<end>\])"
    rb"|/(?P<name>[^\s/<>\[\]()%]*)|\((?P<string>(?:\\.|[^\\)])*)\)|<(?P<hex>[0-9A-Fa-f\s]*)>"
    rb"|(?P<ref>\d+)\s+\d+\s+R\b|(?P<number>[-+]?(?:\d+\.?\d*|\.\d+))|(?P<word>true|false|null))",
    re.S,
)
ESCAPES: Final = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


@dataclass(frozen=True)
class Ref:
    """A reference to an indirect object, by its number."""

    number: int


Object = dict[str, "Object"] | list["Object"] | str | bytes | int | float | bool | Ref | None
"""A PDF object read: a dictionary, an array, a name as `str`, a string as `bytes`, a number,
a boolean, null, or a reference to another object."""
Dict = dict[str, Object]


def unescaped(string: bytes) -> bytes:
    return re.sub(
        rb"\\([0-7]{1,3}|.)",
        lambda m: bytes([int(m[1], 8)]) if m[1][:1].isdigit() else ESCAPES.get(m[1], m[1]),
        string,
        flags=re.S,
    )


def closes(data: bytes, at: int, group: str) -> int | None:
    """Where the token at a place ends, if it is the one that closes a dictionary or an array."""
    token = TOKEN.match(data, at)
    return token.end() if token is not None and token.lastgroup == group else None


def parse(data: bytes, at: int = 0) -> tuple[Object, int]:
    """The object at a place in the bytes, and where it ends."""
    token = TOKEN.match(data, at)
    assert token is not None, f"no PDF object at {data[at : at + 20]!r}"
    kind, end = token.lastgroup, token.end()
    if kind == "open":
        found: Dict = {}
        while (closed := closes(data, end, "close")) is None:
            key, end = parse(data, end)
            found[str(key)], end = parse(data, end)
        return found, closed
    if kind == "start":
        items: list[Object] = []
        while (closed := closes(data, end, "end")) is None:
            item, end = parse(data, end)
            items.append(item)
        return items, closed
    text = token[kind or "word"]
    match kind:
        case "name":
            return text.decode("latin-1"), end
        case "string":
            return unescaped(text), end
        case "hex":
            return bytes.fromhex(re.sub(rb"\s", b"", text).decode()), end
        case "ref":
            return Ref(int(text)), end
        case "number":
            return (float(text) if b"." in text else int(text)), end
        case _:
            return {b"true": True, b"false": False}.get(text), end


class Pdf:
    """A `.pdf`'s objects, by number, the latest of each, with object streams read as theirs."""

    def __init__(self, content: bytes) -> None:
        self.content = content
        self.objects: dict[int, bytes] = {}
        self.streams: dict[int, bytes] = {}
        packed: list[int] = []
        trailer: Dict | None = None
        for header in HEADER.finditer(content):
            number, (head, end) = int(header[1]), parse(content, header.end())
            self.objects[number] = content[header.end() : end]
            if not isinstance(head, dict) or not (stream := STREAM.match(content, end)):
                continue
            length = head.get("Length")
            assert isinstance(length, int), "the corpus' streams' lengths are direct"
            raw = content[stream.end() : stream.end() + length]
            deflated = head.get("Filter") == "FlateDecode"
            self.streams[number] = zlib.decompress(raw) if deflated else raw
            if head.get("Type") == "ObjStm":
                packed.append(number)
            if head.get("Type") == "XRef":
                trailer = head
        for number in packed:
            self._unpack(number)
        self.trailer: Dict = trailer or self._trailer()

    def _unpack(self, number: int) -> None:
        head, _ = parse(self.objects.pop(number))
        assert isinstance(head, dict)
        data, first, count = self.streams.pop(number), head["First"], head["N"]
        assert isinstance(first, int)
        assert isinstance(count, int)
        pairs = [int(n) for n in data[:first].split()]
        for index in range(count):
            packed, offset = pairs[2 * index], pairs[2 * index + 1]
            self.objects.setdefault(packed, data[first + offset :])

    def _trailer(self) -> Dict:
        at = self.content.rindex(b"trailer") + len(b"trailer")
        found, _ = parse(self.content, at)
        assert isinstance(found, dict)
        return found

    def get(self, value: Object) -> Object:
        """An object, resolved if it is a reference."""
        return parse(self.objects[value.number])[0] if isinstance(value, Ref) else value

    def mapping(self, value: Object) -> Dict:
        found = self.get(value)
        return found if isinstance(found, dict) else {}

    def array(self, value: Object) -> list[Object]:
        found = self.get(value)
        return found if isinstance(found, list) else []

    @property
    def catalog(self) -> Dict:
        return self.mapping(self.trailer["Root"])

    def pages(self) -> list[tuple[int, Dict]]:
        """Each page, in order: its object's number and its dictionary."""

        def walk(node: Object) -> list[tuple[int, Dict]]:
            found = self.mapping(node)
            if found.get("Type") == "Page":
                assert isinstance(node, Ref)
                return [(node.number, found)]
            return [page for kid in self.array(found.get("Kids")) for page in walk(kid)]

        return walk(self.catalog["Pages"])

    def page_of(self, value: Object) -> int | None:
        """The place, from 1, of the page a reference names."""
        numbers = [number for number, _ in self.pages()]
        return numbers.index(value.number) + 1 if isinstance(value, Ref) else None

    def annotations(self, subtype: str) -> list[tuple[int, Dict]]:
        return [
            (place, annotation)
            for place, (_, page) in enumerate(self.pages(), 1)
            for ref in self.array(page.get("Annots"))
            if (annotation := self.mapping(ref)).get("Subtype") == subtype
        ]


def rect(value: Object) -> tuple[float, ...]:
    numbers = value if isinstance(value, list) else []
    return tuple(round(float(n), 1) for n in numbers if isinstance(n, int | float))


def text(pdf: Pdf) -> Value:
    """Each page's strings, as its content shows them."""
    found: Value = []
    for place, (_, page) in enumerate(pdf.pages(), 1):
        contents = page.get("Contents")
        refs = contents if isinstance(contents, list) else [contents]
        shown = b"".join(pdf.streams[ref.number] for ref in refs if isinstance(ref, Ref))
        found += [
            (place, unescaped(s).decode("latin-1"))
            for s in re.findall(rb"\(((?:\\.|[^\\)])*)\)\s*Tj", shown)
        ]
    return found


def pages(pdf: Pdf) -> Value:
    """Each page's size and rotation."""
    return [(rect(page.get("MediaBox")), page.get("Rotate", 0)) for _, page in pdf.pages()]


def metadata(pdf: Pdf) -> Value:
    info = pdf.mapping(pdf.trailer.get("Info"))
    return [(key, info.get(key)) for key in ("Title", "Author", "Subject", "Keywords")]


def bookmarks(pdf: Pdf) -> Value:
    """Each bookmark's depth, title and the page it goes to."""

    def walk(item: Object, depth: int) -> Value:
        found: Value = []
        while item is not None:
            entry = pdf.mapping(item)
            dest = pdf.array(entry.get("Dest"))
            found.append((depth, entry.get("Title"), pdf.page_of(dest[0] if dest else None)))
            found += walk(entry.get("First"), depth + 1)
            item = entry.get("Next")
        return found

    return walk(pdf.mapping(pdf.catalog.get("Outlines")).get("First"), 0)


def comments(pdf: Pdf) -> Value:
    return [
        (place, note.get("T"), note.get("Contents"), rect(note.get("Rect")))
        for place, note in pdf.annotations("Text")
    ]


def links(pdf: Pdf) -> Value:
    """Each link's page, place, and where it goes: a URL, or a page."""
    found: Value = []
    for place, link in pdf.annotations("Link"):
        action = pdf.mapping(link.get("A"))
        dest = pdf.array(link.get("Dest"))
        goes = action.get("URI") if action else pdf.page_of(dest[0] if dest else None)
        found.append((place, rect(link.get("Rect")), goes))
    return found


def forms(pdf: Pdf) -> Value:
    """Each field's name, type and value."""
    fields = pdf.array(pdf.mapping(pdf.catalog.get("AcroForm")).get("Fields"))
    return [
        (field.get("T"), field.get("FT"), field.get("V"))
        for field in (pdf.mapping(ref) for ref in fields)
    ]


def page_labels(pdf: Pdf) -> Value:
    """Each range of labels: the page it starts at, from 0, its style and its first number."""
    nums = pdf.array(pdf.mapping(pdf.catalog.get("PageLabels")).get("Nums"))
    return [
        (start, (label := pdf.mapping(style)).get("S"), label.get("St", 1))
        for start, style in zip(nums[::2], nums[1::2], strict=True)
    ]


def images(pdf: Pdf) -> Value:
    """Each image a page draws: its size, and its pixels, by digest."""
    found: Value = []
    for place, (_, page) in enumerate(pdf.pages(), 1):
        for ref in pdf.mapping(pdf.mapping(page.get("Resources")).get("XObject")).values():
            image = pdf.mapping(ref)
            if image.get("Subtype") == "Image" and isinstance(ref, Ref):
                pixels = hashlib.sha256(pdf.streams[ref.number]).hexdigest()
                found.append((place, image.get("Width"), image.get("Height"), pixels))
    return found


READERS: Final[dict[str, Callable[[Pdf], Value]]] = {
    "text": text,
    "pages": pages,
    "metadata": metadata,
    "bookmarks": bookmarks,
    "comments": comments,
    "links": links,
    "forms": forms,
    "page_labels": page_labels,
    "images": images,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in a `.pdf`."""
    return READERS[feature](Pdf(content))


def kept(content: bytes) -> dict[int, bytes]:
    """What saving twice must leave as it was: every object but those that say where the others
    lie, with the date each save stamps blanked, and each stream inflated."""
    pdf = Pdf(content)
    stamped = re.compile(rb"/ModDate\s*\((?:\\.|[^\\)])*\)")
    return {
        number: stamped.sub(b"", body) + pdf.streams.get(number, b"")
        for number, body in pdf.objects.items()
        if pdf.mapping(Ref(number)).get("Type") != "XRef"
    }
