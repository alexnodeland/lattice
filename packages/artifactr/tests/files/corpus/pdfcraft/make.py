"""PdfCraft's corpus: one generated `.pdf` per feature, beside this, each holding that feature.

Every file is written by hand, object by object, from the PDF 1.7 specification's smallest valid
shapes, with its cross-reference table counted from the bytes, so the same code makes the same
bytes. A test fails if the committed files drift from what this makes;
`python -m tests.files.corpus.pdfcraft.make`, from `packages/artifactr`, writes them again.
"""

import zlib
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

HERE: Final = Path(__file__).parent

FONT: Final = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"


def stream(data: bytes, entries: str = "") -> str:
    """A stream object of the bytes, deflated, with the dictionary's other entries."""
    deflated = zlib.compress(data, 9)
    return (
        f"<< /Length {len(deflated)} /Filter /FlateDecode {entries}>>\nstream\n"
        + deflated.decode("latin-1")
        + "\nendstream"
    )


def pdf(objects: Sequence[str], trailer: str = "") -> bytes:
    """A PDF of the objects, numbered from 1, the first its catalog."""
    out = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    offsets: list[int] = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body.encode("latin-1") + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets)
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R {trailer}>>\nstartxref\n{xref}\n%%EOF\n"
    ).encode()
    return out


def page(content: str, *, extra: str = "", size: str = "0 0 612 792") -> str:
    """A page of its content stream's object, with Helvetica as F1, and what else it holds."""
    return (
        f"<< /Type /Page /Parent 2 0 R /MediaBox [{size}] /Contents {content} "
        f"/Resources << /Font << /F1 3 0 R >> >> {extra}>>"
    )


def words(*lines: str) -> str:
    """A content stream of lines of text, from the top of a letter page down."""
    shown = " ".join(f"({line}) Tj 0 -28 Td" for line in lines)
    return stream(f"BT /F1 18 Tf 72 720 Td {shown} ET".encode())


def document(
    pages: Sequence[tuple[str, str]],
    *,
    catalog: str = "",
    more: Sequence[str] = (),
    trailer: str = "",
) -> bytes:
    """A PDF of pages, each its page dictionary, `CONTENT` for its content's reference, and its
    content stream; then the objects after them, numbered on from the last page's content; and
    the catalog's and the trailer's other entries."""
    first = 4
    kids = " ".join(f"{first + 2 * n} 0 R" for n in range(len(pages)))
    objects = [
        f"<< /Type /Catalog /Pages 2 0 R {catalog}>>",
        f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>",
        FONT,
    ]
    for number, (entries, content) in enumerate(pages):
        objects += [entries.replace("CONTENT", f"{first + 2 * number + 1} 0 R"), content]
    return pdf([*objects, *more], trailer)


def text() -> bytes:
    return document([(page("CONTENT"), words("The parties agree to the terms.", "Signed in May."))])


def pages() -> bytes:
    return document(
        [
            (page("CONTENT"), words("Portrait")),
            (page("CONTENT", size="0 0 792 612"), words("Landscape")),
            (page("CONTENT", extra="/Rotate 90"), words("Turned")),
        ]
    )


def metadata() -> bytes:
    info = (
        "<< /Title (Annual report) /Author (Ada) /Subject (Results) /Keywords (revenue, costs) >>"
    )
    return document([(page("CONTENT"), words("Report"))], more=[info], trailer="/Info 6 0 R ")


def bookmarks() -> bytes:
    # Objects 4 to 7 are the pages and their content; 8 the outline; 9 to 11 its items.
    outline = "<< /Type /Outlines /First 9 0 R /Last 10 0 R /Count 3 >>"
    items = [
        "<< /Title (Introduction) /Parent 8 0 R /Next 10 0 R /Dest [4 0 R /Fit] >>",
        "<< /Title (Results) /Parent 8 0 R /Prev 9 0 R /First 11 0 R /Last 11 0 R /Count 1 "
        "/Dest [6 0 R /Fit] >>",
        "<< /Title (By region) /Parent 10 0 R /Dest [6 0 R /XYZ 0 792 0] >>",
    ]
    return document(
        [(page("CONTENT"), words("Introduction")), (page("CONTENT"), words("Results"))],
        catalog="/Outlines 8 0 R /PageMode /UseOutlines ",
        more=[outline, *items],
    )


def comments() -> bytes:
    note = (
        "<< /Type /Annot /Subtype /Text /Rect [72 700 92 720] /Contents (Check this figure.) "
        "/T (Ada) /Name /Comment >>"
    )
    return document(
        [(page("CONTENT", extra="/Annots [6 0 R]"), words("Revenue: 120"))], more=[note]
    )


def links() -> bytes:
    web = (
        "<< /Type /Annot /Subtype /Link /Rect [72 690 300 720] /Border [0 0 0] "
        "/A << /S /URI /URI (https://example.com/) >> >>"
    )
    inside = (
        "<< /Type /Annot /Subtype /Link /Rect [72 650 300 680] /Border [0 0 0] "
        "/Dest [6 0 R /Fit] >>"
    )
    return document(
        [
            (page("CONTENT", extra="/Annots [8 0 R 9 0 R]"), words("The site", "Page two")),
            (page("CONTENT"), words("Two")),
        ],
        more=[web, inside],
    )


def forms() -> bytes:
    name = (
        "<< /Type /Annot /Subtype /Widget /FT /Tx /T (name) /V (Ada Lovelace) "
        "/Rect [72 650 300 670] /P 4 0 R /DA (/Helv 12 Tf 0 g) /F 4 >>"
    )
    agreed = (
        "<< /Type /Annot /Subtype /Widget /FT /Btn /T (agreed) /V /Yes /AS /Yes "
        "/Rect [72 600 90 618] /P 4 0 R /F 4 /AP << /N << /Yes 8 0 R /Off 8 0 R >> >> >>"
    )
    return document(
        [(page("CONTENT", extra="/Annots [6 0 R 7 0 R]"), words("Name:", "Agreed:"))],
        catalog="/AcroForm << /Fields [6 0 R 7 0 R] /DA (/Helv 12 Tf 0 g) "
        "/DR << /Font << /Helv 3 0 R >> >> >> ",
        more=[
            name,
            agreed,
            stream(b"0 g 0 0 18 18 re f", "/Type /XObject /Subtype /Form /BBox [0 0 18 18] "),
        ],
    )


def page_labels() -> bytes:
    return document(
        [
            (page("CONTENT"), words("Preface")),
            (page("CONTENT"), words("Body")),
            (page("CONTENT"), words("More")),
        ],
        catalog="/PageLabels << /Nums [0 << /S /r >> 1 << /S /D /St 1 >>] >> ",
    )


def images() -> bytes:
    width, height = 16, 8
    gradient = bytes(c for y in range(height) for x in range(width) for c in (x * 16, y * 32, 128))
    picture = stream(
        gradient,
        f"/Type /XObject /Subtype /Image /Width {width} /Height {height} "
        "/ColorSpace /DeviceRGB /BitsPerComponent 8 ",
    )
    shown = stream(b"q 160 0 0 80 72 600 cm /Im1 Do Q")
    entries = (
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents CONTENT "
        "/Resources << /XObject << /Im1 6 0 R >> >> >>"
    )
    return document([(entries, shown)], more=[picture])


FEATURES: Final[dict[str, Callable[[], bytes]]] = {
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
"""Each feature RFC-0003's report compares, and what makes its file."""


def main() -> None:
    for feature, make in FEATURES.items():
        (HERE / f"{feature}.pdf").write_bytes(make())


if __name__ == "__main__":
    main()
