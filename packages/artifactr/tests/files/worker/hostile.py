"""The hostile corpus: `.docx` files made to exhaust whatever reads them (lattice RFC-0003).

Each is generated as it is asked for, since the point of most is how large it becomes: none is
committed. Every one is a valid package around one part that is not what its size says.
"""

import io
import struct
import zipfile
import zlib
from collections.abc import Callable
from typing import Final

from tests.files.corpus.package import TIME, png
from tests.files.corpus.wordcraft.make import package


def zip_bomb() -> bytes:
    """A document whose one paragraph inflates to 4 GiB of the same letter."""
    small = package("<w:p/>")
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(small)) as source,
        zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive,
    ):
        for info in source.infolist():
            if info.filename != "word/document.xml":
                archive.writestr(info, source.read(info))
                continue
            head, _, tail = source.read(info).partition(b"<w:p/>")
            entry = zipfile.ZipInfo(info.filename, TIME)
            entry.compress_type = zipfile.ZIP_DEFLATED
            with archive.open(entry, "w", force_zip64=True) as part:
                part.write(head + b"<w:p><w:r><w:t>")
                chunk = b"a" * (64 << 20)
                for _ in range(64):
                    part.write(chunk)
                part.write(b"</w:t></w:r></w:p>" + tail)
    return buffer.getvalue()


def nested_xml() -> bytes:
    """A document whose body nests a million elements, one inside the next."""
    depth = 1_000_000
    return package("<w:customXml>" * depth + "<w:p/>" + "</w:customXml>" * depth)


def enormous_image() -> bytes:
    """A document holding a PNG whose header says it is 65,535 pixels a side."""
    tiny = png(1, 1)
    header = struct.pack(">IIBBBBB", 65_535, 65_535, 8, 2, 0, 0, 0)
    body = b"IHDR" + header
    ihdr = struct.pack(">I", len(header)) + body + struct.pack(">I", zlib.crc32(body))
    image = tiny[:8] + ihdr + tiny[8 + 25 :]
    drawing = (
        '<w:p><w:r><w:drawing><wp:inline><wp:extent cx="914400" cy="914400"/>'
        '<wp:docPr id="1" name="huge"/><a:graphic><a:graphicData '
        'uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
        '<pic:nvPicPr><pic:cNvPr id="1" name="huge.png"/><pic:cNvPicPr/></pic:nvPicPr>'
        '<pic:blipFill><a:blip r:embed="rId9"/></pic:blipFill><pic:spPr/></pic:pic>'
        "</a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>"
    )
    return package(drawing, parts={"rId9": ("image", "media/huge.png", image)})


HOSTILE: Final[dict[str, Callable[[], bytes]]] = {
    "zip_bomb": zip_bomb,
    "nested_xml": nested_xml,
    "enormous_image": enormous_image,
}
