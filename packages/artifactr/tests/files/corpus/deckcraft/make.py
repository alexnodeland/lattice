"""DeckCraft's corpus: one generated `.pptx` per feature, beside this, each holding that feature.

Every file is written by hand, part by part, from the PresentationML schema's smallest valid
shapes, with a fixed time on every zip entry, so the same code makes the same bytes. A test fails
if the committed files drift from what this makes; `python -m tests.files.corpus.deckcraft.make`,
from `packages/artifactr`, writes them again.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from tests.files.corpus.package import RELS, XML, png, relationships, types, zipped

HERE: Final = Path(__file__).parent

P: Final = "http://schemas.openxmlformats.org/presentationml/2006/main"
A: Final = "http://schemas.openxmlformats.org/drawingml/2006/main"
R: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
MAIN: Final = "application/vnd.openxmlformats-officedocument.presentationml"
DRAWING: Final = "application/vnd.openxmlformats-officedocument"
EMU: Final = 12700
"""EMUs a point."""

NAMESPACES: Final = f'xmlns:a="{A}" xmlns:r="{R}" xmlns:p="{P}"'

THEME: Final = (
    f'{XML}<a:theme xmlns:a="{A}" name="Corpus"><a:themeElements>'
    '<a:clrScheme name="Corpus"><a:dk1><a:srgbClr val="000000"/></a:dk1>'
    '<a:lt1><a:srgbClr val="FFFFFF"/></a:lt1><a:dk2><a:srgbClr val="1F2937"/></a:dk2>'
    '<a:lt2><a:srgbClr val="F3F4F6"/></a:lt2><a:accent1><a:srgbClr val="2563EB"/></a:accent1>'
    '<a:accent2><a:srgbClr val="DC2626"/></a:accent2><a:accent3><a:srgbClr val="16A34A"/>'
    '</a:accent3><a:accent4><a:srgbClr val="CA8A04"/></a:accent4><a:accent5>'
    '<a:srgbClr val="9333EA"/></a:accent5><a:accent6><a:srgbClr val="0891B2"/></a:accent6>'
    '<a:hlink><a:srgbClr val="2563EB"/></a:hlink><a:folHlink><a:srgbClr val="7C3AED"/>'
    "</a:folHlink></a:clrScheme>"
    '<a:fontScheme name="Corpus"><a:majorFont><a:latin typeface="Arial"/><a:ea typeface=""/>'
    '<a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Arial"/>'
    '<a:ea typeface=""/><a:cs typeface=""/></a:minorFont></a:fontScheme>'
    '<a:fmtScheme name="Corpus"><a:fillStyleLst>'
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3
    + "</a:fillStyleLst><a:lnStyleLst>"
    + '<a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill></a:ln>' * 3
    + "</a:lnStyleLst><a:effectStyleLst>"
    + "<a:effectStyle><a:effectLst/></a:effectStyle>" * 3
    + "</a:effectStyleLst><a:bgFillStyleLst>"
    + '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>' * 3
    + "</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>"
)
"""The smallest whole theme: its colours, its fonts, and three of each format style."""

TREE: Final = (
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/>'
    '<a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
)
"""What every shape tree starts with: the tree itself, as a group."""

MASTER: Final = (
    f"{XML}<p:sldMaster {NAMESPACES}><p:cSld><p:spTree>{TREE}</p:spTree></p:cSld>"
    '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" '
    'accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" '
    'folHlink="folHlink"/><p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/>'
    "</p:sldLayoutIdLst></p:sldMaster>"
)

LAYOUT: Final = (
    f'{XML}<p:sldLayout {NAMESPACES} type="obj"><p:cSld name="Title and Content"><p:spTree>'
    f"{TREE}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>"
)


def box(x: int, y: int, w: int, h: int) -> str:
    """A shape's place and size, in points."""
    return (
        f'<a:xfrm><a:off x="{x * EMU}" y="{y * EMU}"/><a:ext cx="{w * EMU}" cy="{h * EMU}"/>'
        "</a:xfrm>"
    )


def run(text: str, props: str = "", inner: str = "") -> str:
    """A run of text, with its properties' attributes and what they hold, such as a fill."""
    rpr = (
        f'<a:rPr lang="en-US"{props}>{inner}</a:rPr>' if inner else f'<a:rPr lang="en-US"{props}/>'
    )
    return f"<a:r>{rpr}<a:t>{text}</a:t></a:r>"


def paragraph(*runs: str, level: int = 0) -> str:
    ppr = f'<a:pPr lvl="{level}"/>' if level else ""
    return f"<a:p>{ppr}{''.join(runs)}</a:p>"


def shape(sid: int, name: str, paragraphs: str, *, at: str = "", kind: str = "") -> str:
    """A shape of text: a placeholder of a kind, such as `title`, or a text box at a place."""
    placeholder = f'<p:nvPr><p:ph type="{kind}"/></p:nvPr>' if kind else "<p:nvPr/>"
    return (
        f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="{name}"/><p:cNvSpPr/>{placeholder}'
        f"</p:nvSpPr><p:spPr>{at}</p:spPr><p:txBody><a:bodyPr/><a:lstStyle/>{paragraphs}"
        "</p:txBody></p:sp>"
    )


def title(text: str) -> str:
    return shape(2, "Title 1", paragraph(run(text)), at=box(60, 30, 840, 100), kind="title")


@dataclass(frozen=True)
class Slide:
    """A slide: its shapes, and what it holds beside them."""

    shapes: str
    after: str = ""
    """What follows its shape tree, such as its transition."""

    notes: str = ""
    hidden: bool = False
    parts: Mapping[str, tuple[str, str, bytes | str]] = field(
        default_factory=dict[str, tuple[str, str, bytes | str]]
    )
    """The parts it names, `{id: (type, target from ppt/, content)}`."""

    links: Mapping[str, str] = field(default_factory=dict[str, str])
    """Its external links, `{id: url}`."""


def deck(*slides: Slide, size: tuple[int, int] = (960, 540), more: str = "") -> bytes:
    """A `.pptx` of the slides, in order, at a size in points, and what else its presentation
    holds, such as its comment authors' part."""
    overrides = {
        "ppt/presentation.xml": f"{MAIN}.presentation.main+xml",
        "ppt/slideMasters/slideMaster1.xml": f"{MAIN}.slideMaster+xml",
        "ppt/slideLayouts/slideLayout1.xml": f"{MAIN}.slideLayout+xml",
        "ppt/theme/theme1.xml": f"{DRAWING}.theme+xml",
    }
    files: dict[str, bytes | str] = {}
    targets = {
        "rId1": ("slideMaster", "slideMasters/slideMaster1.xml"),
        "rId2": ("theme", "theme/theme1.xml"),
    }
    listed: list[str] = []
    for number, slide in enumerate(slides, 1):
        part = f"ppt/slides/slide{number}.xml"
        hidden = ' show="0"' if slide.hidden else ""
        files[part] = (
            f"{XML}<p:sld {NAMESPACES}{hidden}><p:cSld><p:spTree>{TREE}{slide.shapes}"
            f"</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr>"
            f"{slide.after}</p:sld>"
        )
        overrides[part] = f"{MAIN}.slide+xml"
        targets[f"rId{number + 9}"] = ("slide", f"slides/slide{number}.xml")
        listed.append(f'<p:sldId id="{255 + number}" r:id="rId{number + 9}"/>')
        own = {"rId1": ("slideLayout", "../slideLayouts/slideLayout1.xml")}
        for rid, (kind, target, content) in slide.parts.items():
            own[rid] = (kind, f"../{target}")
            files[f"ppt/{target}"] = content
            if not target.endswith(".png"):
                overrides[f"ppt/{target}"] = f"{MAIN}.{kind}+xml"
        if slide.notes:
            notes = f"ppt/notesSlides/notesSlide{number}.xml"
            own["rId9"] = ("notesSlide", f"../notesSlides/notesSlide{number}.xml")
            files[notes] = (
                f"{XML}<p:notes {NAMESPACES}><p:cSld><p:spTree>{TREE}"
                + shape(2, "Notes Placeholder 2", paragraph(run(slide.notes)), kind="body")
                + "</p:spTree></p:cSld></p:notes>"
            )
            overrides[notes] = f"{MAIN}.notesSlide+xml"
            files[f"ppt/notesSlides/_rels/notesSlide{number}.xml.rels"] = relationships(
                {"rId1": ("slide", f"../slides/slide{number}.xml")}
            )
        links = {rid: ("hyperlink", url) for rid, url in slide.links.items()}
        files[f"ppt/slides/_rels/slide{number}.xml.rels"] = relationships(own, links)
    if more:
        targets["rId3"] = ("commentAuthors", "commentAuthors.xml")
        files["ppt/commentAuthors.xml"] = more
        overrides["ppt/commentAuthors.xml"] = f"{MAIN}.commentAuthors+xml"
    width, height = size
    return zipped(
        {
            "[Content_Types].xml": types(
                {"rels": RELS, "xml": "application/xml", "png": "image/png"}, overrides
            ),
            "_rels/.rels": relationships({"rId1": ("officeDocument", "ppt/presentation.xml")}),
            "ppt/presentation.xml": (
                f"{XML}<p:presentation {NAMESPACES}><p:sldMasterIdLst>"
                '<p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
                f"<p:sldIdLst>{''.join(listed)}</p:sldIdLst>"
                f'<p:sldSz cx="{width * EMU}" cy="{height * EMU}"/>'
                '<p:notesSz cx="6858000" cy="9144000"/></p:presentation>'
            ),
            "ppt/_rels/presentation.xml.rels": relationships(targets),
            "ppt/slideMasters/slideMaster1.xml": MASTER,
            "ppt/slideMasters/_rels/slideMaster1.xml.rels": relationships(
                {
                    "rId1": ("slideLayout", "../slideLayouts/slideLayout1.xml"),
                    "rId2": ("theme", "../theme/theme1.xml"),
                }
            ),
            "ppt/slideLayouts/slideLayout1.xml": LAYOUT,
            "ppt/slideLayouts/_rels/slideLayout1.xml.rels": relationships(
                {"rId1": ("slideMaster", "../slideMasters/slideMaster1.xml")}
            ),
            "ppt/theme/theme1.xml": THEME,
            **files,
        }
    )


def text() -> bytes:
    body = paragraph(run("Revenue grew in every region.")) + paragraph(run("Costs held flat."))
    content = shape(3, "Content 2", body, at=box(60, 140, 840, 340), kind="body")
    return deck(Slide(title("Results") + content))


def slides() -> bytes:
    return deck(
        Slide(title("Opening")),
        Slide(title("Backup"), hidden=True),
        Slide(title("Closing")),
    )


def text_formatting() -> bytes:
    runs = [
        run("bold", ' b="1"'),
        run("italic", ' i="1"'),
        run("underlined", ' u="sng"'),
        run("large", ' sz="4400"'),
        run("red", inner='<a:solidFill><a:srgbClr val="FF0000"/></a:solidFill>'),
    ]
    return deck(Slide(shape(3, "Text 2", paragraph(*runs), at=box(60, 60, 840, 200))))


def bullets() -> bytes:
    body = (
        paragraph(run("First"))
        + paragraph(run("Nested"), level=1)
        + paragraph(run("Deeper"), level=2)
        + paragraph(run("Second"))
    )
    return deck(Slide(shape(3, "Content 2", body, at=box(60, 60, 840, 400), kind="body")))


def notes() -> bytes:
    return deck(Slide(title("Agenda"), notes="Welcome everyone, then the numbers."))


def tables() -> bytes:
    rows = [["Region", "Revenue"], ["North", "120"], ["South", "95"]]
    grid = '<a:gridCol w="2540000"/>' * 2
    cells = "".join(
        '<a:tr h="370840">'
        + "".join(
            f"<a:tc><a:txBody><a:bodyPr/><a:lstStyle/>{paragraph(run(c))}</a:txBody><a:tcPr/></a:tc>"
            for c in row
        )
        + "</a:tr>"
        for row in rows
    )
    frame = (
        '<p:graphicFrame><p:nvGraphicFramePr><p:cNvPr id="4" name="Table 3"/>'
        '<p:cNvGraphicFramePr><a:graphicFrameLocks noGrp="1"/></p:cNvGraphicFramePr><p:nvPr/>'
        f'</p:nvGraphicFramePr><p:xfrm><a:off x="{60 * EMU}" y="{60 * EMU}"/>'
        f'<a:ext cx="5080000" cy="1112520"/></p:xfrm><a:graphic><a:graphicData '
        f'uri="{A}/table"><a:tbl><a:tblPr firstRow="1"/><a:tblGrid>{grid}</a:tblGrid>{cells}'
        "</a:tbl></a:graphicData></a:graphic></p:graphicFrame>"
    )
    return deck(Slide(frame))


def images() -> bytes:
    picture = (
        '<p:pic><p:nvPicPr><p:cNvPr id="4" name="Picture 3" descr="A gradient"/><p:cNvPicPr/>'
        '<p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed="rId2"/><a:stretch><a:fillRect/>'
        f'</a:stretch></p:blipFill><p:spPr>{box(100, 100, 200, 150)}<a:prstGeom prst="rect">'
        "<a:avLst/></a:prstGeom></p:spPr></p:pic>"
    )
    return deck(Slide(picture, parts={"rId2": ("image", "media/image1.png", png(32, 24))}))


def shapes() -> bytes:
    def preset(sid: int, geometry: str, color: str, at: str) -> str:
        return (
            f'<p:sp><p:nvSpPr><p:cNvPr id="{sid}" name="Shape {sid}"/><p:cNvSpPr/><p:nvPr/>'
            f'</p:nvSpPr><p:spPr>{at}<a:prstGeom prst="{geometry}"><a:avLst/></a:prstGeom>'
            f'<a:solidFill><a:srgbClr val="{color}"/></a:solidFill></p:spPr></p:sp>'
        )

    drawn = preset(3, "ellipse", "2563EB", box(100, 100, 120, 120)) + preset(
        4, "rightArrow", "16A34A", box(300, 140, 200, 60)
    )
    return deck(Slide(drawn))


def transitions() -> bytes:
    return deck(Slide(title("Fade in"), after='<p:transition spd="slow"><p:fade/></p:transition>'))


def hyperlinks() -> bytes:
    linked = run("The site", inner='<a:hlinkClick r:id="rId5"/>')
    body = shape(3, "Text 2", paragraph(linked), at=box(60, 60, 400, 60))
    return deck(Slide(body, links={"rId5": "https://example.com/"}))


def slide_size() -> bytes:
    return deck(Slide(title("Four by three")), size=(720, 540))


def comments() -> bytes:
    authors = (
        f'{XML}<p:cmAuthorLst {NAMESPACES}><p:cmAuthor id="0" name="Ada" initials="A" '
        'lastIdx="1" clrIdx="0"/></p:cmAuthorLst>'
    )
    notes = (
        f'{XML}<p:cmLst {NAMESPACES}><p:cm authorId="0" dt="2026-10-01T09:00:00.000" idx="1">'
        '<p:pos x="10" y="10"/><p:text>Check these numbers.</p:text></p:cm></p:cmLst>'
    )
    slide = Slide(title("Numbers"), parts={"rId3": ("comments", "comments/comment1.xml", notes)})
    return deck(slide, more=authors)


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
    "text": text,
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
"""Each feature RFC-0003's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.pptx").write_bytes(make())


if __name__ == "__main__":
    main()
