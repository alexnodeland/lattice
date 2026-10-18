"""WordCraft's corpus: one generated `.docx` per feature, beside this, each holding that feature.

Every file is written by hand, part by part, from the OOXML schema's smallest valid shapes, with
a fixed time on every zip entry, so the same code makes the same bytes. A test fails if the
committed files drift from what this makes; `python -m tests.files.corpus.wordcraft.make`, from
`packages/artifactr`, writes them again.
"""

import io
import struct
import zipfile
import zlib
from collections.abc import Callable
from pathlib import Path
from typing import Final

HERE: Final = Path(__file__).parent
TIME: Final = (2026, 10, 17, 0, 0, 0)

W: Final = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL: Final = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG: Final = "http://schemas.openxmlformats.org/package/2006/relationships"
WP: Final = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A: Final = "http://schemas.openxmlformats.org/drawingml/2006/main"
PIC: Final = "http://schemas.openxmlformats.org/drawingml/2006/picture"
MAIN: Final = "application/vnd.openxmlformats-officedocument.wordprocessingml"
RELS: Final = "application/vnd.openxmlformats-package.relationships+xml"
XML: Final = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'


def png(width: int, height: int) -> bytes:
    """A PNG of a gradient, so its bytes are an image's and not a blank's."""

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    rows = b"".join(
        b"\0" + b"".join(bytes((x * 255 // width, y * 255 // height, 128)) for x in range(width))
        for y in range(height)
    )
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows, 9))
        + chunk(b"IEND", b"")
    )


def p(text: str, *, props: str = "", run: str = "") -> str:
    """A paragraph of one run."""
    ppr = f"<w:pPr>{props}</w:pPr>" if props else ""
    rpr = f"<w:rPr>{run}</w:rPr>" if run else ""
    return f'<w:p>{ppr}<w:r>{rpr}<w:t xml:space="preserve">{text}</w:t></w:r></w:p>'


def package(
    body: str,
    *,
    parts: dict[str, tuple[str, str, bytes | str]] | None = None,
    section: str = "",
) -> bytes:
    """A `.docx` of a body, and the parts it names: `{id: (type, target, content)}`.

    A part's type is its relationship's, after `.../relationships/`, which also names its content
    type; `image` parts are PNGs.
    """
    parts = parts or {}
    types = [
        f'<Default Extension="rels" ContentType="{RELS}"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Default Extension="png" ContentType="image/png"/>',
        f'<Override PartName="/word/document.xml" ContentType="{MAIN}.document.main+xml"/>',
    ]
    rels: list[str] = []
    files: dict[str, bytes | str] = {}
    for rid, (kind, target, content) in parts.items():
        rels.append(f'<Relationship Id="{rid}" Type="{REL}/{kind}" Target="{target}"/>')
        files[f"word/{target}"] = content
        if kind != "image":
            types.append(f'<Override PartName="/word/{target}" ContentType="{MAIN}.{kind}+xml"/>')
    sect = section or (
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" w:header="720" '
        'w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document xmlns:w="{W}" '
        f'xmlns:r="{R}" xmlns:wp="{WP}" xmlns:a="{A}" xmlns:pic="{PIC}"><w:body>{body}{sect}'
        "</w:body></w:document>"
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Types xmlns='
            f'"http://schemas.openxmlformats.org/package/2006/content-types">{"".join(types)}'
            "</Types>"
        ),
        "_rels/.rels": (
            f'{XML}<Relationships xmlns="{PKG}">'
            f'<Relationship Id="rId1" Type="{REL}/officeDocument" Target="word/document.xml"/>'
            "</Relationships>"
        ),
        "word/document.xml": document,
        "word/_rels/document.xml.rels": (
            f'{XML}<Relationships xmlns="{PKG}">{"".join(rels)}</Relationships>'
        ),
        **files,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            data = content.encode() if isinstance(content, str) else content
            archive.writestr(zipfile.ZipInfo(name, TIME), data, zipfile.ZIP_DEFLATED)
    return buffer.getvalue()


def part(root: str, inner: str) -> str:
    """A part's XML: its root element, in WordprocessingML's namespace, around what it holds."""
    return (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<w:{root} xmlns:w="{W}" xmlns:r="{R}">{inner}</w:{root}>'
    )


def text() -> bytes:
    return package(p("The parties agree to the terms below.") + p("Signed on the first of May."))


def styles() -> bytes:
    defined = "".join(
        f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/></w:style>'
        for sid, name in [("Normal", "Normal"), ("Heading1", "heading 1"), ("Title", "Title")]
    )
    body = (
        p("Contract", props='<w:pStyle w:val="Title"/>')
        + p("Terms", props='<w:pStyle w:val="Heading1"/>')
        + p("Pay within thirty days.")
    )
    return package(body, parts={"rId1": ("styles", "styles.xml", part("styles", defined))})


def run_properties() -> bytes:
    runs = [
        ("bold", "<w:b/>"),
        ("italic", "<w:i/>"),
        ("underlined", '<w:u w:val="single"/>'),
        ("red", '<w:color w:val="FF0000"/>'),
        ("large", '<w:sz w:val="36"/>'),
        ("struck", "<w:strike/>"),
    ]
    return package("".join(p(t, run=rpr) for t, rpr in runs))


def tables() -> bytes:
    rows = [["Item", "Fee"], ["Setup", "100"], ["Support", "20"]]
    cells = "".join(
        "<w:tr>"
        + "".join(
            f'<w:tc><w:tcPr><w:tcW w:w="2000" w:type="dxa"/></w:tcPr>{p(c)}</w:tc>' for c in row
        )
        + "</w:tr>"
        for row in rows
    )
    table = (
        '<w:tbl><w:tblPr><w:tblW w:w="4000" w:type="dxa"/></w:tblPr>'
        f'<w:tblGrid><w:gridCol w:w="2000"/><w:gridCol w:w="2000"/></w:tblGrid>{cells}</w:tbl>'
    )
    return package(p("Fees:") + table + p("All fees are in euros."))


def lists() -> bytes:
    def level(ilvl: int, fmt: str) -> str:
        return (
            f'<w:lvl w:ilvl="{ilvl}"><w:start w:val="1"/><w:numFmt w:val="{fmt}"/>'
            f'<w:lvlText w:val="%{ilvl + 1}."/></w:lvl>'
        )

    numbering = part(
        "numbering",
        f'<w:abstractNum w:abstractNumId="0">{level(0, "decimal")}{level(1, "lowerLetter")}'
        f'</w:abstractNum><w:abstractNum w:abstractNumId="1">{level(0, "bullet")}</w:abstractNum>'
        '<w:num w:numId="1"><w:abstractNumId w:val="0"/></w:num>'
        '<w:num w:numId="2"><w:abstractNumId w:val="1"/></w:num>',
    )

    def item(t: str, num: int, ilvl: int) -> str:
        return p(t, props=f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num}"/></w:numPr>')

    body = item("First", 1, 0) + item("Nested", 1, 1) + item("Second", 1, 0) + item("Dot", 2, 0)
    return package(body, parts={"rId1": ("numbering", "numbering.xml", numbering)})


def images() -> bytes:
    emu = 914400
    drawing = (
        f'<w:p><w:r><w:drawing><wp:inline><wp:extent cx="{emu}" cy="{emu}"/>'
        '<wp:docPr id="1" name="Picture 1"/><a:graphic><a:graphicData '
        f'uri="{PIC}"><pic:pic><pic:nvPicPr><pic:cNvPr id="1" name="dots.png"/><pic:cNvPicPr/>'
        '</pic:nvPicPr><pic:blipFill><a:blip r:embed="rId1"/><a:stretch><a:fillRect/></a:stretch>'
        f'</pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{emu}" cy="{emu}"/>'
        '</a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic>'
        "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
    )
    return package(
        p("A picture:") + drawing, parts={"rId1": ("image", "media/image1.png", png(16, 16))}
    )


def headers_and_footers() -> bytes:
    section = (
        '<w:sectPr><w:headerReference w:type="default" r:id="rId1"/>'
        '<w:footerReference w:type="default" r:id="rId2"/>'
        '<w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" '
        'w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    return package(
        p("The body."),
        parts={
            "rId1": ("header", "header1.xml", part("hdr", p("Confidential"))),
            "rId2": ("footer", "footer1.xml", part("ftr", p("Page footer"))),
        },
        section=section,
    )


def footnotes() -> bytes:
    notes = part(
        "footnotes",
        '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
        '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/>'
        '</w:r></w:p></w:footnote><w:footnote w:id="1"><w:p><w:r><w:footnoteRef/></w:r>'
        '<w:r><w:t xml:space="preserve"> As amended in 2025.</w:t></w:r></w:p></w:footnote>',
    )
    body = (
        '<w:p><w:r><w:t xml:space="preserve">The statute applies.</w:t></w:r>'
        '<w:r><w:footnoteReference w:id="1"/></w:r></w:p>'
    )
    return package(body, parts={"rId1": ("footnotes", "footnotes.xml", notes)})


def comments() -> bytes:
    notes = part(
        "comments",
        '<w:comment w:id="0" w:author="Ada" w:date="2026-10-01T09:00:00Z" w:initials="A">'
        f"{p('Check the dates.')}</w:comment>",
    )
    body = (
        '<w:p><w:commentRangeStart w:id="0"/><w:r><w:t>Due on the first of May.</w:t></w:r>'
        '<w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r></w:p>'
    )
    return package(body, parts={"rId1": ("comments", "comments.xml", notes)})


def tracked_changes() -> bytes:
    body = (
        '<w:p><w:r><w:t xml:space="preserve">The fee is </w:t></w:r>'
        '<w:del w:id="1" w:author="Ada" w:date="2026-10-01T09:00:00Z"><w:r>'
        "<w:delText>100</w:delText></w:r></w:del>"
        '<w:ins w:id="2" w:author="Ada" w:date="2026-10-01T09:00:00Z"><w:r><w:t>120</w:t></w:r>'
        '</w:ins><w:r><w:t xml:space="preserve"> euros.</w:t></w:r></w:p>'
    )
    return package(body)


def sections() -> bytes:
    portrait = (
        '<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1440" w:right="1440" '
        'w:bottom="1440" w:left="1440" w:header="720" w:footer="720" w:gutter="0"/></w:sectPr>'
    )
    landscape = (
        '<w:sectPr><w:pgSz w:w="15840" w:h="12240" w:orient="landscape"/><w:pgMar w:top="720" '
        'w:right="720" w:bottom="720" w:left="720" w:header="360" w:footer="360" w:gutter="0"/>'
        '<w:cols w:num="2" w:space="720"/></w:sectPr>'
    )
    body = p("A portrait page.", props=portrait) + p("Two columns, landscape.")
    return package(body, section=landscape)


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
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
"""Each feature RFC-0003's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.docx").write_bytes(make())


if __name__ == "__main__":
    main()
