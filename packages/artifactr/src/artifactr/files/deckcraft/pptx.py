"""What the adapter reads from a `.pptx`: its fingerprint, its format, its outline and text.

A `.pptx` is a zip of XML parts. DeckCraft stamps nothing on a save, but writes a deck it made
in other XML than the same deck reopened, `<a:p/>` for `<a:p></a:p>` and namespaces declared
again, so the fingerprint is the digest of every part, each XML part in its canonical form.
"""

from collections.abc import Sequence
from typing import Final

from pydantic import BaseModel

from artifactr.files.craft import Package
from artifactr.files.manifest import OUTLINE_LIMIT, PPTX

MAIN: Final = {
    "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml": PPTX,
    "application/vnd.ms-powerpoint.presentation.macroEnabled.main+xml": (
        "application/vnd.ms-powerpoint.presentation.macroEnabled.12"
    ),
    "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.slideshow"
    ),
    "application/vnd.openxmlformats-officedocument.presentationml.template.main+xml": (
        "application/vnd.openxmlformats-officedocument.presentationml.template"
    ),
}
"""A presentation package's main part's content type, and the media type of a file it is the
main of."""

PPTX_PACKAGE: Final = Package(".pptx", main=MAIN, canonical=True)


def media_type(content: bytes) -> str | None:
    """The format a presentation package or an OpenDocument says it is, or None if it says none.

    As [`Package.media_type`][artifactr.files.craft.Package.media_type] reads it.
    """
    return PPTX_PACKAGE.media_type(content)


def fingerprint(content: bytes, *, limit: int) -> str:
    """The digest of a `.pptx`'s parts, by name, each XML part in its canonical form.

    As [`Package.fingerprint`][artifactr.files.craft.Package.fingerprint] reads it.
    """
    return PPTX_PACKAGE.fingerprint(content, limit=limit)


class Table(BaseModel):
    """A table's cells, by row, as `inspect_slide` gives them."""

    cells: list[list[str]] = []


class Shape(BaseModel):
    """A shape of `inspect_slide`, as far as the text reads it."""

    text: str = ""
    table: Table | None = None


class Slide(BaseModel):
    """A slide of `inspect_slide`, as far as the outline and the text read it."""

    title: str = ""
    notes: str = ""
    shapes: list[Shape] = []


def outline(slides: Sequence[Slide]) -> str:
    """Each slide's title, by its number from 1; a slide without one is left out."""
    titled = (f"{number}. {slide.title}" for number, slide in enumerate(slides, 1) if slide.title)
    return "\n".join(titled)[:OUTLINE_LIMIT]


def text(slides: Sequence[Slide]) -> str:
    """Each slide's words: its shapes' text, its tables a line a row, then its notes."""

    def words(slide: Slide) -> list[str]:
        found: list[str] = []
        for shape in slide.shapes:
            found += [shape.text] if shape.text else []
            found += ["\t".join(row) for row in shape.table.cells] if shape.table else []
        return [*found, slide.notes] if slide.notes else found

    return "\n\n".join("\n".join(words(slide)) for slide in slides)
