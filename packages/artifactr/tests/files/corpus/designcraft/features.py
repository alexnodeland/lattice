"""Each feature of an IDML package, read out of its XML into a value two saves can be compared by.

A value keeps what the feature means and leaves out what a save may rewrite without changing
it: the ids of stories, frames and styles, which are numbered again, the order the parts are
listed in, and the defaults a save writes out. The fidelity report opens and saves each corpus
file in DesignCraft and compares its feature's value before and after (lattice RFC-0003,
phase 2).
"""

import io
import zipfile
from collections.abc import Callable
from typing import Final
from xml.etree import ElementTree

Value = list[tuple[object, ...]]


class Idml:
    """An IDML package's parts: its designmap's spreads and stories, and its resources."""

    def __init__(self, content: bytes) -> None:
        self._zip = zipfile.ZipFile(io.BytesIO(content))
        self.designmap = self.xml("designmap.xml")

    def xml(self, name: str) -> ElementTree.Element:
        return ElementTree.fromstring(self._zip.read(name))

    def listed(self, kind: str) -> list[ElementTree.Element]:
        """The parts the designmap lists of a kind, `Spread` or `Story`, in its order."""
        return [
            self.xml(part.get("src", ""))
            for part in self.designmap
            if part.tag.endswith(f"}}{kind}")
        ]

    def stories(self) -> dict[str, ElementTree.Element]:
        found: dict[str, ElementTree.Element] = {}
        for part in self.listed("Story"):
            for story in part.iter("Story"):
                found[story.get("Self", "")] = story
        return found

    def frames(self) -> list[tuple[int, ElementTree.Element]]:
        """Each text frame, with the number of the spread it is on, from 0."""
        return [
            (number, frame)
            for number, part in enumerate(self.listed("Spread"))
            for frame in part.iter("TextFrame")
        ]

    def styles(self, kind: str) -> dict[str, ElementTree.Element]:
        """Each style of a kind, `ParagraphStyle` or `CharacterStyle`, by its `Self`."""
        return {
            style.get("Self", ""): style for style in self.xml("Resources/Styles.xml").iter(kind)
        }


def paragraphs(story: ElementTree.Element) -> list[str]:
    """A story's paragraphs' words, split at each break."""
    said: list[str] = []
    for element in story.iter():
        if element.tag == "Content":
            said.append(element.text or "")
        elif element.tag == "Br":
            said.append("\n")
    return "".join(said).split("\n")


def text_of(idml: Idml, frame: ElementTree.Element) -> str:
    return "\n".join(paragraphs(idml.stories()[frame.get("ParentStory", "")]))


def bounds(frame: ElementTree.Element) -> tuple[float, ...]:
    """A frame's corners on its spread: its path's anchors, moved by its transform."""
    a, b, c, d, tx, ty = (float(n) for n in frame.get("ItemTransform", "1 0 0 1 0 0").split())
    points = [
        tuple(float(n) for n in anchor.get("Anchor", "0 0").split())
        for anchor in frame.iter("PathPointType")
    ]
    moved = [(a * x + c * y + tx, b * x + d * y + ty) for x, y in points]
    xs, ys = [x for x, _ in moved], [y for _, y in moved]
    return tuple(round(n, 3) for n in (min(xs), min(ys), max(xs), max(ys)))


def text(idml: Idml) -> Value:
    return sorted((tuple(paragraphs(story)),) for story in idml.stories().values())


def paragraph_styles(idml: Idml) -> Value:
    """Each paragraph's style, by its name, size and alignment, and its words."""
    defined = idml.styles("ParagraphStyle")
    found: Value = []
    for story in idml.stories().values():
        for styled in story.iter("ParagraphStyleRange"):
            style = defined.get(styled.get("AppliedParagraphStyle", ""), ElementTree.Element(""))
            words = "".join(content.text or "" for content in styled.iter("Content"))
            if words:
                found.append(
                    (style.get("Name"), style.get("PointSize"), style.get("Justification"), words)
                )
    return found


def character_styles(idml: Idml) -> Value:
    """Each run's style, by its name and font style, and its words."""
    defined = idml.styles("CharacterStyle")
    return [
        (
            style.get("Name"),
            style.get("FontStyle"),
            "".join(c.text or "" for c in run.iter("Content")),
        )
        for story in idml.stories().values()
        for run in story.iter("CharacterStyleRange")
        if (style := defined.get(run.get("AppliedCharacterStyle", ""))) is not None
        and run.find("Content") is not None
    ]


def pages(idml: Idml) -> Value:
    """Each spread's pages, by name and bounds, and the words on it."""
    found: Value = []
    for number, part in enumerate(idml.listed("Spread")):
        named = tuple((p.get("Name"), p.get("GeometricBounds")) for p in part.iter("Page"))
        words = tuple(text_of(idml, f) for n, f in idml.frames() if n == number)
        found.append((named, words))
    return found


def frames(idml: Idml) -> Value:
    return [(number, bounds(f), text_of(idml, f)) for number, f in idml.frames()]


def threaded_frames(idml: Idml) -> Value:
    """Each story's frames, by their bounds, in the order its text flows through them."""
    by_id = {f.get("Self", ""): f for _, f in idml.frames()}
    found: Value = []
    for _, frame in idml.frames():
        if frame.get("PreviousTextFrame", "n") != "n":
            continue
        chain: list[tuple[float, ...]] = []
        current: ElementTree.Element | None = frame
        while current is not None:
            chain.append(bounds(current))
            current = by_id.get(current.get("NextTextFrame", "n"))
        found.append((text_of(idml, frame)[:20], tuple(chain)))
    return found


def values(color: ElementTree.Element) -> tuple[float, ...]:
    return tuple(round(float(n), 2) for n in color.get("ColorValue", "").split())


def colors(idml: Idml) -> Value:
    """Each frame's fill, by its colour's name, space and values, which a save writes in floats."""
    graphic = idml.xml("Resources/Graphic.xml")
    defined = {color.get("Self", ""): color for color in graphic.iter("Color")}
    found: Value = []
    for _, frame in idml.frames():
        color = defined.get(frame.get("FillColor", ""))
        if color is not None:
            found.append(
                (color.get("Name"), color.get("Space"), values(color), text_of(idml, frame))
            )
    return found


READERS: Final[dict[str, Callable[[Idml], Value]]] = {
    "text": text,
    "paragraph_styles": paragraph_styles,
    "character_styles": character_styles,
    "pages": pages,
    "frames": frames,
    "threaded_frames": threaded_frames,
    "colors": colors,
}


def read(feature: str, content: bytes) -> Value:
    """A feature's value in an IDML package."""
    return READERS[feature](Idml(content))
