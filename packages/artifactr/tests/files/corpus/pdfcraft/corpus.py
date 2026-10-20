"""PdfCraft's corpus: a `.pdf` per feature, each feature's value read out of its objects."""

import zlib

from artifactr.files.app import App
from artifactr.files.pdfcraft import Subprocess
from tests.files.corpus.harness import Corpus
from tests.files.corpus.pdfcraft.features import kept, read
from tests.files.corpus.pdfcraft.make import FEATURES, FONT, HERE, document, page, pdf, words


def adapter(cli: str, version: str) -> App:
    return Subprocess(cli, version=version)


def cycle() -> bytes:
    """A document whose page tree is its own child: no page is ever reached."""
    tree = "<< /Type /Pages /Kids [2 0 R] /Count 1 >>"
    return pdf(["<< /Type /Catalog /Pages 2 0 R >>", tree, FONT, page("5 0 R"), words("Lost")])


def locked() -> bytes:
    """A document encrypted with a password no one is given."""
    secret = f"<< /Filter /Standard /V 1 /R 2 /Length 40 /P -4 /O <{'ab' * 32}> /U <{'cd' * 32}> >>"
    objects = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [4 0 R] /Count 1 >>"]
    return pdf(
        [*objects, FONT, page("5 0 R"), words("Secret"), secret],
        f"/Encrypt 6 0 R /ID [<{'00' * 16}> <{'00' * 16}>] ",
    )


def bomb() -> bytes:
    """A document whose object stream inflates to 300 MiB from 300 KiB, a MiB at a time."""
    deflater = zlib.compressobj(9)
    packed = b"".join(deflater.compress(b" " * (1 << 20)) for _ in range(300)) + deflater.flush()
    stream = (
        f"<< /Type /ObjStm /N 1 /First 4 /Length {len(packed)} /Filter /FlateDecode >>\nstream\n"
        + packed.decode("latin-1")
        + "\nendstream"
    )
    return document([(page("CONTENT"), words("Packed"))], more=[stream])


def headers() -> bytes:
    """A document of nothing but 200,000 objects' headers, none of them ended."""
    return b"%PDF-1.7\n" + b"1 0 obj\n" * 200_000


CORPUS = Corpus(
    app="pdfcraft",
    extension=".pdf",
    folder=HERE,
    makers=FEATURES,
    read=read,
    kept=kept,
    adapter=adapter,
    hostile={"cycle": cycle, "locked": locked, "bomb": bomb, "headers": headers},
)
"""PdfCraft 0.8.0 keeps every feature."""
