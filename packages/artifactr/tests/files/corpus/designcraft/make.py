"""DesignCraft's corpus: one generated `.idml` per feature, beside this, each holding that feature.

Every package is written by hand, part by part, from IDML's smallest valid shapes: its `mimetype`
first and stored, then its designmap, resources, spreads and stories, with a fixed time on every
zip entry, so the same code makes the same bytes. A test fails if the committed files drift from
what this makes; `python -m tests.files.corpus.designcraft.make`, from `packages/artifactr`,
writes them again.
"""

import io
import zipfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

HERE: Final = Path(__file__).parent
TIME: Final = (2026, 10, 20, 0, 0, 0)
PKG: Final = "http://ns.adobe.com/AdobeInDesign/idml/1.0/packaging"
XML: Final = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
MIMETYPE: Final = "application/vnd.adobe.indesign-idml-package"
PAGE: Final = (612, 792)
"""A page's width and height, in points: US Letter."""


@dataclass(frozen=True)
class Frame:
    """A text frame on a page: its story, its bounds `(x0, y0, x1, y1)`, and the frames its
    text flows from and into."""

    story: str
    bounds: tuple[int, int, int, int]
    fill: str = "Swatch/None"
    after: str = "n"
    before: str = "n"
    name: str = ""


@dataclass(frozen=True)
class Layout:
    """A layout: its pages' frames, its stories' XML by id, and its styles and colours."""

    pages: Sequence[Sequence[Frame]]
    stories: dict[str, str]
    paragraph_styles: str = ""
    character_styles: str = ""
    colors: str = ""
    frames: dict[str, int] = field(default_factory=dict[str, int])


def paragraph(text: str, *, style: str = "$ID/NormalParagraphStyle", ranges: str = "") -> str:
    """A paragraph of one run of text, or of the character ranges it is given."""
    runs = ranges or (
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">'
        f"<Content>{text}</Content></CharacterStyleRange>"
    )
    return (
        f'<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/{style}">{runs}'
        "</ParagraphStyleRange>"
    )


def run(text: str, style: str = "$ID/[No character style]") -> str:
    return (
        f'<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/{style}">'
        f"<Content>{text}</Content></CharacterStyleRange>"
    )


def br() -> str:
    """A paragraph break, between two paragraphs."""
    return (
        '<ParagraphStyleRange AppliedParagraphStyle="ParagraphStyle/$ID/NormalParagraphStyle">'
        '<CharacterStyleRange AppliedCharacterStyle="CharacterStyle/$ID/[No character style]">'
        "<Br/></CharacterStyleRange></ParagraphStyleRange>"
    )


def _frame(frame: Frame, own: str, top: int) -> str:
    x0, y0, x1, y1 = frame.bounds
    points = "".join(
        f'<PathPointType Anchor="{x} {y}" LeftDirection="{x} {y}" RightDirection="{x} {y}"/>'
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    )
    return (
        f'<TextFrame Self="{own}" ParentStory="{frame.story}" PreviousTextFrame="{frame.before}" '
        f'NextTextFrame="{frame.after}" ContentType="TextType" Name="{frame.name or "$ID/"}" '
        f'ItemLayer="layer" FillColor="{frame.fill}" StrokeColor="Swatch/None" '
        f'ItemTransform="1 0 0 1 0 {top}"><Properties><PathGeometry>'
        f'<GeometryPathType PathOpen="false"><PathPointArray>{points}</PathPointArray>'
        "</GeometryPathType></PathGeometry></Properties></TextFrame>"
    )


def package(layout: Layout) -> bytes:
    """An IDML package of a layout: a spread for each page, and a story for each story."""
    width, height = PAGE
    parts: dict[str, str] = {
        "META-INF/container.xml": (
            f'{XML}<container version="1.0" '
            'xmlns="urn:oasis:names:tc:opendocument:xmlns:container">'
            '<rootfiles><rootfile full-path="designmap.xml" media-type="text/xml"/></rootfiles>'
            "</container>"
        ),
        "Resources/Graphic.xml": (
            f'{XML}<idPkg:Graphic xmlns:idPkg="{PKG}" DOMVersion="16.0">'
            '<Color Self="Color/Black" Model="Process" Space="CMYK" ColorValue="0 0 0 100" '
            f'Name="Black"/>{layout.colors}<Swatch Self="Swatch/None" Name="None"/>'
            "</idPkg:Graphic>"
        ),
        "Resources/Styles.xml": (
            f'{XML}<idPkg:Styles xmlns:idPkg="{PKG}" DOMVersion="16.0">'
            '<RootCharacterStyleGroup Self="chars"><CharacterStyle '
            'Self="CharacterStyle/$ID/[No character style]" Name="$ID/[No character style]"/>'
            f"{layout.character_styles}</RootCharacterStyleGroup>"
            '<RootParagraphStyleGroup Self="paras"><ParagraphStyle '
            'Self="ParagraphStyle/$ID/NormalParagraphStyle" Name="$ID/NormalParagraphStyle" '
            f'PointSize="12"/>{layout.paragraph_styles}</RootParagraphStyleGroup>'
            # DesignCraft adds both table styles to a package that lacks them, in an order its
            # next save turns round: given as that save writes them, the first save is a fixpoint.
            '<RootTableStyleGroup Self="tables"><TableStyle Self="TableStyle/$ID/[Basic Table]" '
            'Name="$ID/[Basic Table]"/><TableStyle Self="TableStyle/$ID/[No table style]" '
            'Name="$ID/[No table style]"/></RootTableStyleGroup></idPkg:Styles>'
        ),
    }
    spreads: list[str] = []
    for index, frames in enumerate(layout.pages):
        top = -height // 2
        items = "".join(
            _frame(frame, f"frame{index}_{number}", top) for number, frame in enumerate(frames)
        )
        own = f"spread{index}"
        parts[f"Spreads/Spread_{own}.xml"] = (
            f'{XML}<idPkg:Spread xmlns:idPkg="{PKG}" DOMVersion="16.0"><Spread Self="{own}" '
            f'PageCount="1" BindingLocation="0" ItemTransform="1 0 0 1 0 0"><Page '
            f'Self="page{index}" Name="{index + 1}" GeometricBounds="0 0 {height} {width}" '
            f'ItemTransform="1 0 0 1 0 {top}"/>{items}</Spread></idPkg:Spread>'
        )
        spreads.append(own)
    for own, xml in layout.stories.items():
        parts[f"Stories/Story_{own}.xml"] = (
            f'{XML}<idPkg:Story xmlns:idPkg="{PKG}" DOMVersion="16.0"><Story Self="{own}">'
            f"{xml}</Story></idPkg:Story>"
        )
    designmap = (
        f'{XML}<Document xmlns:idPkg="{PKG}" DOMVersion="16.0" Self="d" '
        f'StoryList="{" ".join(layout.stories)}" Name="corpus.indd" ActiveLayer="layer">'
        '<idPkg:Graphic src="Resources/Graphic.xml"/><idPkg:Styles src="Resources/Styles.xml"/>'
        '<Layer Self="layer" Name="Layer 1" Visible="true" Locked="false" Printable="true"/>'
        + "".join(f'<idPkg:Spread src="Spreads/Spread_{own}.xml"/>' for own in spreads)
        + "".join(f'<idPkg:Story src="Stories/Story_{own}.xml"/>' for own in layout.stories)
        + "</Document>"
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(zipfile.ZipInfo("mimetype", TIME), MIMETYPE, zipfile.ZIP_STORED)
        archive.writestr(zipfile.ZipInfo("designmap.xml", TIME), designmap, zipfile.ZIP_DEFLATED)
        for name, xml in parts.items():
            archive.writestr(zipfile.ZipInfo(name, TIME), xml, zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


BOX: Final = (36, 36, 300, 200)


def text() -> bytes:
    story = paragraph("The parties agree to the terms below.") + br() + paragraph("Signed in May.")
    return package(Layout(pages=[[Frame("s1", BOX)]], stories={"s1": story}))


def paragraph_styles() -> bytes:
    defined = (
        '<ParagraphStyle Self="ParagraphStyle/Heading" Name="Heading" PointSize="24" '
        'Justification="CenterAlign"/>'
    )
    story = paragraph("Contract", style="Heading") + br() + paragraph("Pay within thirty days.")
    return package(
        Layout(pages=[[Frame("s1", BOX)]], stories={"s1": story}, paragraph_styles=defined)
    )


def character_styles() -> bytes:
    defined = '<CharacterStyle Self="CharacterStyle/Emphasis" Name="Emphasis" FontStyle="Italic"/>'
    story = paragraph("", ranges=run("Pay ") + run("within thirty days", "Emphasis") + run("."))
    return package(
        Layout(pages=[[Frame("s1", BOX)]], stories={"s1": story}, character_styles=defined)
    )


def pages() -> bytes:
    stories = {f"s{n}": paragraph(f"Page {n}") for n in (1, 2, 3)}
    return package(Layout(pages=[[Frame(own, BOX)] for own in stories], stories=stories))


def frames() -> bytes:
    stories = {"s1": paragraph("Left"), "s2": paragraph("Right")}
    placed = [Frame("s1", (36, 36, 290, 500)), Frame("s2", (322, 36, 576, 300))]
    return package(Layout(pages=[placed], stories=stories))


def threaded_frames() -> bytes:
    words = " ".join(["Flowing"] * 120)
    placed = [
        Frame("s1", (36, 36, 290, 120), after="frame0_1"),
        Frame("s1", (322, 36, 576, 120), before="frame0_0"),
    ]
    return package(Layout(pages=[placed], stories={"s1": paragraph(words)}))


def colors() -> bytes:
    defined = (
        '<Color Self="Color/Brand" Model="Process" Space="RGB" ColorValue="200 30 60" '
        'Name="Brand"/>'
    )
    placed = [Frame("s1", BOX, fill="Color/Brand")]
    return package(Layout(pages=[placed], stories={"s1": paragraph("Coloured")}, colors=defined))


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
    "text": text,
    "paragraph_styles": paragraph_styles,
    "character_styles": character_styles,
    "pages": pages,
    "frames": frames,
    "threaded_frames": threaded_frames,
    "colors": colors,
}
"""Each feature DesignCraft's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.idml").write_bytes(make())


if __name__ == "__main__":
    main()
